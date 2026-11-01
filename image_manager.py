"""Explicit local image imports and reversible, previewed folder synchronization.

Original bytes are retained. A scan only writes the catalogue and a review plan;
only apply() may replace or archive a picture. There is no background watcher.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
import unicodedata
from urllib.parse import urlencode, urlsplit
import uuid

from PIL import Image


EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.ico'}
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_FILES = 3000
META = '.image-manager'


class ImageManagerError(ValueError):
    status = 400

    def __init__(self, message, *, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows ordinary readers may briefly deny delete-sharing.
                # Keep the fully flushed temporary file and atomic replacement;
                # a persistent denial still reaches the caller unchanged.
                if attempt == 7:
                    raise
                time.sleep(min(0.01 * 2 ** attempt, 0.1))
    finally:
        temporary.unlink(missing_ok=True)


def _json(path, default):
    if not path.exists():
        return default
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ImageManagerError('图片管理记录过大，请先检查记录。', status=409)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as error:
        raise ImageManagerError('图片管理记录无法读取；原图保持不变。', status=409) from error


def _link(path):
    information = path.lstat()
    return stat.S_ISLNK(information.st_mode) or bool(getattr(information, 'st_file_attributes', 0) & 0x400)


def _safe_directory(value):
    if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
        raise ImageManagerError('请选择已存在的完整文件夹路径。')
    path = Path(os.path.abspath(value))
    for part in (path, *path.parents):
        if part.exists() and _link(part):
            raise ImageManagerError('图库不能使用符号链接或目录联接。')
    if not path.is_dir():
        raise ImageManagerError('所选文件夹不存在。')
    return path


def _identity(path):
    value = path.stat()
    return [str(value.st_dev), str(value.st_ino)]


def _inside(root, value, *, private=False):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        raise ImageManagerError('图片相对路径无效。')
    parts = value.split('/')
    if any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in parts):
        raise ImageManagerError('图片路径不可离开图库。')
    if not private and parts[0].casefold() == META:
        raise ImageManagerError('不能直接访问图片管理内部记录。')
    candidate = root.joinpath(*parts)
    for part in (candidate, *candidate.parents):
        if part == root.parent:
            break
        if part.exists() and _link(part):
            raise ImageManagerError('图片路径不能经过链接。')
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ImageManagerError('图片路径不可离开图库。')
    return candidate


def _title(name):
    value = unicodedata.normalize('NFC', Path(name).stem)
    value = re.sub(r'(?:\s*[-_－–—]?\s*)[\[(（]?\d{1,6}\s*[xX×＊*]\s*\d{1,6}[\])）]?(?:\s+\(\d{1,6}\))?(?=(?:[_ -]v\d+)?$)', '', value).strip(' -_－–—')
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:140] or 'Image'
    if re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', value):
        value = '_' + value
    return value


def _annotation_text(value, label, maximum):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ImageManagerError(f'{label}必须为 1 至 {maximum} 字，不能含控制字符。')
    return unicodedata.normalize('NFC', value.strip())


def _group_id(title):
    return 'group-' + hashlib.sha256(title.casefold().encode('utf-8')).hexdigest()[:24]


def _filename_annotation(title):
    # Notion may normalize the marker's separator spaces to underscores. Only
    # recognize those structural separators; underscores in names stay literal.
    match = re.fullmatch(r'(.+?)(?:\s+|_)\[方案(?: |_)([^\[\]]{1,100})\]', title)
    if match:
        return (_annotation_text(match[1], '图片组名称', 140),
                _annotation_text(match[2], '方案名称', 100))
    return title, None


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata(path, root, space='root'):
    before = path.stat()
    if before.st_size > MAX_IMAGE_BYTES:
        raise ImageManagerError('图片超过单张 64 MiB 限制。')
    if path.suffix.lower() not in EXTENSIONS or not stat.S_ISREG(before.st_mode) or before.st_nlink > 1:
        raise ImageManagerError('只接受普通 PNG、JPEG、WebP、GIF、BMP 或 TIFF 图片。')
    digest = _sha(path)
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise ImageManagerError('图片超过 4000 万像素，暂不进行解码比较。')
            animated = getattr(image, 'n_frames', 1) > 1
            has_transparency = None if animated else False
            actual_format = image.format
            # Decode in small strips to avoid allocating a second full RGBA image.
            pixel = hashlib.sha256(f'{width}x{height}:RGBA:'.encode())
            if not animated:
                image.load()
                for y in range(0, height, 64):
                    strip = image.crop((0, y, width, min(height, y + 64))).convert('RGBA')
                    pixel.update(strip.tobytes())
                    has_transparency = has_transparency or strip.getextrema()[3][0] < 255
                    strip.close()
            else:
                image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ImageManagerError('图片无法完整解码，未导入。') from error
    suffixes = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp', 'GIF': '.gif',
                'BMP': '.bmp', 'TIFF': '.tiff', 'ICO': '.ico'}
    if actual_format not in suffixes:
        raise ImageManagerError('图片内容格式不受支持。')
    after = path.stat()
    fingerprint = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if fingerprint(before) != fingerprint(after):
        raise ImageManagerError('图片正在改写，请稍后重新检查。', status=409)
    relative = path.relative_to(root).as_posix()
    title = _title(path.name)
    return {'id': hashlib.sha256((space + ':' + relative).encode()).hexdigest()[:24], 'assetId': digest,
            'path': relative, 'name': path.name, 'title': title, 'width': width, 'height': height,
            'sha256': digest, 'pixelSha256': '' if animated else pixel.hexdigest(),
            'hasTransparency': has_transparency,
            'size': before.st_size, 'mtimeNs': str(before.st_mtime_ns), 'space': space,
            'canonicalName': f'{title} - {width}x{height}{suffixes[actual_format]}',
            'mimeType': Image.MIME.get(actual_format, mimetypes.guess_type(path.name)[0] or 'application/octet-stream'),
            'previewUrl': '/api/images/preview?' + urlencode({'path': relative, 'expectedRoot': str(root), 'space': space})}


def _same(left, right):
    if left['sha256'] == right['sha256']:
        return 'bytes'
    if left.get('pixelSha256') and left['pixelSha256'] == right.get('pixelSha256'):
        return 'pixels'
    if (left['title'].casefold(), left['width'], left['height']) == (right['title'].casefold(), right['width'], right['height']):
        return 'name-size'
    if (left.get('groupId') and left.get('groupId') == right.get('groupId')
            and (left['width'], left['height']) == (right['width'], right['height'])):
        return 'group-size'
    return ''


class ImageManagerService:
    def __init__(self, config_path, document_library=None):
        self.config_path = Path(config_path)
        self.document_library = document_library
        self._mutex = threading.RLock()

    def _config(self):
        result = _json(self.config_path, {})
        if not isinstance(result, dict):
            raise ImageManagerError('图片文件夹配置无法读取。', status=409)
        return result

    def _roots(self, expectedRoot=None):
        config = self._config()
        root = _safe_directory(config.get('root', ''))
        if expectedRoot is not None and os.path.normcase(str(root)) != os.path.normcase(str(expectedRoot)):
            raise ImageManagerError('图库已切换，请重新载入后操作。', status=409)
        if _identity(root) != config.get('rootIdentity'):
            raise ImageManagerError('图库文件夹身份已改变，请重新选择。', status=409)
        device = None
        if config.get('deviceRoot'):
            device = _safe_directory(config['deviceRoot'])
            if _identity(device) != config.get('deviceIdentity'):
                raise ImageManagerError('设备文件夹身份已改变，请重新选择。', status=409)
        return config, root, device

    @contextmanager
    def _locked(self, root):
        with self._mutex:
            directory = _inside(root, META, private=True)
            directory.mkdir(exist_ok=True)
            lock = _inside(root, META + '/write.lock', private=True)
            handle = lock.open('a+b')
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    if lock.stat().st_size == 0:
                        handle.write(b'0')
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                handle.close()
                raise ImageManagerError('此图库有另一项图片操作正在写入。', status=409) from error
            try:
                yield
            finally:
                if not handle.closed:
                    if os.name == 'nt':
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    handle.close()

    def configure(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'root', 'deviceRoot', 'notionPage', 'expectedRoot'}:
            raise ImageManagerError('图片文件夹配置参数无效。')
        with self._mutex:
            previous = self._config()
            if 'expectedRoot' in payload and payload['expectedRoot'] != previous.get('root', ''):
                raise ImageManagerError('图库配置已改变，请重新载入。', status=409)
            root = _safe_directory(payload.get('root', previous.get('root', '')))
            device_value = payload.get('deviceRoot', previous.get('deviceRoot', ''))
            device = _safe_directory(device_value) if device_value else None
            if device and (root == device or root.is_relative_to(device) or device.is_relative_to(root)):
                raise ImageManagerError('设备文件夹与图库必须分开，不能相互包含。')
            notion = payload.get('notionPage', previous.get('notionPage', ''))
            if not isinstance(notion, str) or len(notion) > 2048:
                raise ImageManagerError('Notion 页面地址无效。')
            if notion and not (re.fullmatch(r'[0-9a-fA-F-]{32,36}', notion) or (
                    urlsplit(notion).scheme == 'https' and (urlsplit(notion).hostname or '') in {'notion.so', 'www.notion.so', 'app.notion.com'})):
                raise ImageManagerError('请使用 Notion 页面链接或页面 ID。')
            with self._locked(root):
                inbox = _inside(root, 'inbox')
                inbox.mkdir(exist_ok=True)
                if not inbox.is_dir():
                    raise ImageManagerError('inbox 已存在且不是文件夹。')
                _atomic_json(self.config_path, {'root': str(root), 'rootIdentity': _identity(root),
                    'deviceRoot': str(device) if device else '', 'deviceIdentity': _identity(device) if device else None,
                    'notionPage': notion, 'updatedAt': _now()})
        return self.state()

    def _manifest(self, root):
        result = _json(_inside(root, META + '/library.json', private=True), {'items': [], 'annotations': {}, 'retainedPairs': [], 'lastSync': None})
        if not isinstance(result, dict) or not isinstance(result.get('items'), list):
            raise ImageManagerError('图片索引损坏；原图保持不变。', status=409)
        if not isinstance(result.setdefault('annotations', {}), dict):
            raise ImageManagerError('图片方案注释无法读取；原图保持不变。', status=409)
        return result

    @staticmethod
    def _manifest_version(root):
        path = _inside(root, META + '/library.json', private=True)
        if not path.exists():
            return None
        information = path.stat()
        if not stat.S_ISREG(information.st_mode) or information.st_nlink != 1:
            raise ImageManagerError('设备方案记录不能经过链接或共享文件。', status=409)
        digest = _sha(path)
        after = path.stat()
        fingerprint = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_nlink)
        if fingerprint(information) != fingerprint(after):
            raise ImageManagerError('设备方案记录正在改变，请重新检查。', status=409)
        return [str(information.st_dev), str(information.st_ino), str(information.st_size), str(information.st_mtime_ns), digest]

    def _saved_manifest_version(self, root, expected):
        version = self._manifest_version(root)
        if self._manifest(root) != expected or self._manifest_version(root) != version:
            raise ImageManagerError('设备方案记录保存后又被修改，请重新检查。', status=409)
        return version

    def _device_guard(self, root, device, versions, files=()):
        _, actual_root, actual_device = self._roots(str(root))
        if actual_root != root or actual_device != device:
            raise ImageManagerError('设备同步目标已改变，请重新检查。', status=409)
        for directory, version, identity in versions:
            if _identity(directory) != identity or self._manifest_version(directory) != version:
                raise ImageManagerError('设备同步期间方案信息已改变，请重新检查。', status=409)
        for item, directory in files:
            path = self._fresh(item, {'root':directory, 'device':directory})
            if path.stat().st_nlink != 1:
                raise ImageManagerError('设备图片不能使用共享文件链接。', status=409)
        _, actual_root, actual_device = self._roots(str(root))
        if actual_root != root or actual_device != device or any(_identity(directory) != identity for directory, _, identity in versions):
            raise ImageManagerError('设备同步目标已改变，请重新检查。', status=409)

    @staticmethod
    def _device_entry(item):
        parent = item.get('derivedFromId') or item.get('pendingDerivedFromId') or ''
        if not isinstance(parent, str) or (parent and not re.fullmatch(r'[0-9a-f]{64}', parent)):
            raise ImageManagerError('设备图片的派生来源身份无效。', status=409)
        return {'sha256':item['sha256'],
                'groupTitle':_annotation_text(item['groupTitle'], '图片组名称', 140),
                'variantLabel':_annotation_text(item['variantLabel'], '方案名称', 100),
                'variantExplicit':item.get('variantExplicit') is True, 'derivedFromId':parent}

    def _merge_device_annotations(self, manifest, catalogue, entries):
        annotations = json.loads(json.dumps(manifest['annotations']))
        self._enrich(catalogue, annotations)
        available = {item['sha256'] for item in catalogue}
        changed, unresolved = [], []
        for entry in entries:
            digest, parent = entry['sha256'], entry['derivedFromId']
            if digest not in available:
                raise ImageManagerError('设备目标原图尚未确认，未保存方案信息。', status=409)
            value = annotations[digest]
            before = self._device_entry(dict(value, sha256=digest))
            value.update(groupTitle=entry['groupTitle'], groupId=_group_id(entry['groupTitle']),
                         variantLabel=entry['variantLabel'], variantExplicit=entry['variantExplicit'],
                         derivedFromId=parent if parent in available else '',
                         pendingDerivedFromId=parent if parent and parent not in available else '')
            if before != entry:
                changed.append(digest)
            if parent and parent not in available:
                unresolved.append({'sha256':digest, 'derivedFromId':parent, 'reason':'source_not_local'})
        self._validate_annotation_graph(annotations)
        self._enrich(catalogue, annotations)
        manifest.update(annotations=annotations, items=catalogue)
        return {'applied':len(changed), 'unresolved':len(unresolved), 'unresolvedEntries':unresolved}

    @staticmethod
    def _plan_items(plan):
        result = []
        for candidate in (plan or {}).get('candidates', []):
            result.extend(item for item in [candidate.get('incoming'), candidate.get('existing'),
                                            *candidate.get('matches', [])] if isinstance(item, dict))
        return result

    def _previous_annotation_items(self, root, manifest):
        items = []
        latest = _json(_inside(root, META + '/latest-plan.json', private=True), {})
        identifier = latest.get('planId', '')
        if isinstance(identifier, str) and re.fullmatch(r'[0-9a-f]{32}', identifier):
            plan = _json(_inside(root, META + '/plans/' + identifier + '.json', private=True), {})
            items.extend(item for item in self._plan_items(plan) if item.get('space', 'root') == 'root')
        # The current catalogue wins over an older plan's pre-replacement view.
        items.extend(manifest['items'])
        return items

    @staticmethod
    def _inherit_annotation(value):
        return {**{key:json.loads(json.dumps(value[key])) for key in
                   ('groupTitle','groupId','variantNumber','variantLabel','variantExplicit') if key in value},
                'derivedFromId':'','pendingDerivedFromId':''}

    def _inherit_path_annotations(self, items, previous, annotations):
        self._enrich(previous, annotations)
        by_path = {(item.get('space','root'), item['path'].casefold()):item for item in previous}
        for item in items:
            if item['sha256'] in annotations or _filename_annotation(item['title'])[1] is not None:
                continue
            old = by_path.get((item.get('space','root'), item['path'].casefold()))
            if old and old['sha256'] != item['sha256'] and old['sha256'] in annotations:
                annotations[item['sha256']] = self._inherit_annotation(annotations[old['sha256']])

    @staticmethod
    def _enrich(items, annotations):
        """Project semantic metadata; callers choose whether to persist the map."""
        counters = {}
        for value in annotations.values():
            if not isinstance(value, dict):
                raise ImageManagerError('图片方案注释损坏。', status=409)
            title = value.get('groupTitle')
            number = value.get('variantNumber', 0)
            if title and isinstance(number, int):
                identifier = _group_id(title)
                counters[identifier] = max(counters.get(identifier, 0), number)
        for item in items:
            digest = item.get('sha256', '')
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ImageManagerError('图片身份无法核对。', status=409)
            title, filename_label = _filename_annotation(item['title'])
            annotation = annotations.get(digest)
            if annotation is None:
                group = _group_id(title)
                number = counters.get(group, 0) + 1
                counters[group] = number
                annotation = {'groupTitle': title, 'groupId': group,
                    'variantId': 'variant-' + digest, 'variantNumber': number,
                    'variantLabel': filename_label or f'方案{number}',
                    'variantExplicit': filename_label is not None,
                    'derivedFromId': '', 'pendingDerivedFromId': ''}
                annotations[digest] = annotation
            group_title = _annotation_text(annotation.get('groupTitle', title), '图片组名称', 140)
            annotation['groupId'] = _group_id(group_title)
            item.update({'assetId': digest, 'displayTitle': '透明Logo' if title == 'Togo' else title,
                'groupId': annotation['groupId'], 'groupTitle': group_title,
                'variantId': annotation.setdefault('variantId', 'variant-' + digest),
                'variantLabel': _annotation_text(annotation.get('variantLabel', '方案1'), '方案名称', 100),
                'variantExplicit': annotation.get('variantExplicit') is True,
                'derivedFromId': annotation.get('derivedFromId', ''),
                'pendingDerivedFromId': annotation.get('pendingDerivedFromId', '')})
            item.setdefault('hasTransparency', None)
        available = {item['sha256'] for item in items}
        for annotation in annotations.values():
            pending = annotation.get('pendingDerivedFromId')
            if pending and pending in available:
                annotation.update(derivedFromId=pending, pendingDerivedFromId='')
        for item in items:
            annotation = annotations[item['sha256']]
            item.update(derivedFromId=annotation.get('derivedFromId',''),
                        pendingDerivedFromId=annotation.get('pendingDerivedFromId',''))
        groups = {}
        for item in items:
            groups.setdefault(item['groupId'], set()).add(item['variantId'])
        for item in items:
            explicit_name = item['variantExplicit'] or len(groups[item['groupId']]) > 1
            suffix = Path(item['canonicalName']).suffix
            if explicit_name:
                group = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', item['groupTitle']).strip(' .')[:100] or 'Image'
                label = re.sub(r'[<>:"/\\|?*\[\]\x00-\x1f]', '_', item['variantLabel']).strip(' .')[:100] or '方案'
                item['syncName'] = f"{group} [方案 {label}] - {item['width']}x{item['height']}{suffix}"
            else:
                item['syncName'] = item['canonicalName']
        return items

    @staticmethod
    def _validate_annotation_graph(annotations):
        for identifier in annotations:
            visited = set()
            cursor = identifier
            while cursor:
                if cursor in visited:
                    raise ImageManagerError('派生来源不能指向自己或形成循环。', status=409)
                visited.add(cursor)
                value = annotations.get(cursor, {})
                cursor = value.get('derivedFromId') or value.get('pendingDerivedFromId') or ''

    def _annotation_catalogue(self, root):
        regular, errors = self._files(root)
        pending, pending_errors = self._files(root, inbox=True)
        return regular + pending, errors + pending_errors

    def _write_annotations_locked(self, root, manifest, catalogue, entries, *, allow_missing):
        annotations = json.loads(json.dumps(manifest['annotations']))
        self._inherit_path_annotations(catalogue, self._previous_annotation_items(root, manifest), annotations)
        self._enrich(catalogue, annotations)
        available = {item['sha256']: item for item in catalogue}
        identifiers = {item['id']: item['sha256'] for item in catalogue}
        changed, skipped, unresolved = [], [], []
        requested_graph = json.loads(json.dumps(annotations))
        seen = set()
        for entry in entries:
            if (not isinstance(entry, dict) or set(entry) - {'sha256','groupTitle','variantLabel','derivedFromId'}
                    or not {'sha256','groupTitle','variantLabel'} <= set(entry)):
                raise ImageManagerError('方案目录字段无效。')
            digest = entry['sha256']
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest) or digest in seen:
                raise ImageManagerError('方案目录图片身份无效或重复。')
            seen.add(digest)
            title = _annotation_text(entry['groupTitle'], '图片组名称', 140)
            label = _annotation_text(entry['variantLabel'], '方案名称', 100)
            parent = entry.get('derivedFromId')
            if 'derivedFromId' in entry and (not isinstance(parent, str) or (parent and not re.fullmatch(r'[0-9a-f]{64}', parent))):
                if not allow_missing and isinstance(parent, str) and parent in identifiers:
                    parent = identifiers[parent]
                else:
                    raise ImageManagerError('派生来源身份无效。')
            if parent == digest:
                raise ImageManagerError('图片不能以自己作为派生来源。', status=409)
            if 'derivedFromId' in entry:
                requested_graph[digest] = {'derivedFromId':parent or ''}
            if digest not in available:
                if allow_missing:
                    skipped.append(digest)
                    continue
                raise ImageManagerError('图片已改变或不在当前图库中，请重新检查。', status=409)
            value = annotations[digest]
            value.update(groupTitle=title, groupId=_group_id(title), variantLabel=label, variantExplicit=True)
            if 'derivedFromId' in entry:
                if parent and parent not in available:
                    if not allow_missing:
                        raise ImageManagerError('派生来源不在当前图库中，请先导入来源图片。', status=409)
                    value.update(derivedFromId='', pendingDerivedFromId=parent)
                    unresolved.append({'sha256':digest,'derivedFromId':parent,'reason':'source_not_local'})
                else:
                    value.update(derivedFromId=parent or '', pendingDerivedFromId='')
            changed.append(digest)
        # An explicitly imported pending reference resolves only when its exact
        # source asset is present; no size/name/pixel similarity is used.
        for value in annotations.values():
            pending = value.get('pendingDerivedFromId')
            if pending and pending in available:
                value.update(derivedFromId=pending, pendingDerivedFromId='')
        self._validate_annotation_graph(requested_graph)
        self._validate_annotation_graph(annotations)
        # Revalidate all modified originals at the atomic metadata write boundary.
        guarded = set(changed)
        guarded.update(annotations[digest].get('derivedFromId') for digest in changed)
        for digest in guarded:
            if digest in available:
                self._fresh(available[digest], {'root':root})
        self._roots(str(root))
        manifest['annotations'] = annotations
        self._enrich(manifest['items'], annotations)
        _atomic_json(_inside(root, META + '/library.json', private=True), manifest)
        self._enrich(catalogue, annotations)
        return {'ok':True,'applied':len(changed),'skipped':skipped,'unresolved':unresolved}, catalogue

    def annotate(self, payload):
        if (not isinstance(payload, dict) or set(payload) - {'expectedRoot','path','sha256','groupTitle','variantLabel','derivedFromId','space'}
                or not {'expectedRoot','path','sha256','groupTitle','variantLabel'} <= set(payload)
                or payload.get('space','root') != 'root'):
            raise ImageManagerError('方案标注参数无效。')
        config, root, device = self._roots(payload['expectedRoot'])
        with self._locked(root):
            source = _inside(root, payload['path'])
            if source.suffix.lower() not in EXTENSIONS or (source.is_file() and source.stat().st_size > MAX_IMAGE_BYTES):
                raise ImageManagerError('只可标注大小受支持的图库图片。')
            if not source.is_file() or _sha(source) != payload['sha256']:
                raise ImageManagerError('图片在编辑后已改变，请重新检查再标注。', status=409)
            manifest = self._manifest(root)
            catalogue, errors = self._annotation_catalogue(root)
            matching = [item for item in catalogue if item['sha256'] == payload['sha256']
                        and item['path'].casefold() == payload['path'].casefold()]
            if not matching:
                raise ImageManagerError('图片在编辑后已改变，请重新检查再标注。', status=409)
            catalogue = [item for item in catalogue if item is not matching[0]] + matching[:1]
            entry = {key:payload[key] for key in ('sha256','groupTitle','variantLabel','derivedFromId') if key in payload}
            result, catalogue = self._write_annotations_locked(root, manifest, catalogue, [entry], allow_missing=False)
            item = next(item for item in catalogue if item['sha256'] == payload['sha256']
                        and item['path'].casefold() == payload['path'].casefold())
            return {**result,'item':item,'errors':errors,'state':self.state()}

    def import_annotations(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {'expectedRoot','entries'}
                or not isinstance(payload['entries'], list) or len(payload['entries']) > MAX_FILES):
            raise ImageManagerError('方案目录导入参数无效。')
        config, root, device = self._roots(payload['expectedRoot'])
        with self._locked(root):
            manifest = self._manifest(root)
            catalogue, errors = self._annotation_catalogue(root)
            result, catalogue = self._write_annotations_locked(root, manifest, catalogue, payload['entries'], allow_missing=True)
            return {**result,'errors':errors,'state':self.state()}

    def state(self):
        config = self._config()
        if not config.get('root'):
            return {'configured': False, 'root': '', 'deviceRoot': '', 'notionPage': '',
                    'items': [], 'inboxCount': 0, 'lastSync': None, 'plan': None, 'limits': {'maxFileBytes': MAX_IMAGE_BYTES}}
        config, root, device = self._roots()
        with self._mutex:
            manifest = self._manifest(root)
            inbox = _inside(root, 'inbox')
            count = 0
            if inbox.is_dir():
                for directory, subdirs, files in os.walk(inbox, followlinks=False):
                    subdirs[:] = [name for name in subdirs if not _link(Path(directory) / name)]
                    count += sum(1 for name in files if Path(name).suffix.lower() in EXTENSIONS)
                    if count >= MAX_FILES:
                        break
            latest = _json(_inside(root, META + '/latest-plan.json', private=True), {})
            plan = None
            if re.fullmatch(r'[0-9a-f]{32}', str(latest.get('planId', ''))):
                saved = _json(_inside(root, META + '/plans/' + latest['planId'] + '.json', private=True), {})
                if saved.get('status') == 'review':
                    plan = saved
            annotations = json.loads(json.dumps(manifest['annotations']))
            self._enrich(manifest['items'] + [item for item in self._plan_items(plan)
                         if item.get('space', 'root') == 'root'], annotations)
            return {'configured': True, 'root': str(root), 'deviceRoot': str(device) if device else '',
                    'notionPage': config.get('notionPage', ''), 'items': manifest['items'],
                    'inboxCount': count, 'lastSync': manifest.get('lastSync'), 'plan': plan,
                    'limits': {'maxFileBytes': MAX_IMAGE_BYTES, 'maxPixels': MAX_PIXELS, 'maxFiles': MAX_FILES}}

    def _files(self, root, *, inbox=False, space='root'):
        start = _inside(root, 'inbox') if inbox else root
        if not start.exists():
            return [], []
        result, errors = [], []
        for directory, subdirs, files in os.walk(start, followlinks=False):
            subdirs[:] = sorted(name for name in subdirs if name.casefold() not in {META, 'inbox'} and not _link(Path(directory) / name))
            for name in sorted(files, key=str.casefold):
                target = Path(directory) / name
                if target.suffix.lower() not in EXTENSIONS:
                    continue
                if len(result) + len(errors) >= MAX_FILES:
                    raise ImageManagerError('图片超过单次 3000 张限制，请分批选择文件夹。')
                try:
                    relative = target.relative_to(root).as_posix()
                    _inside(root, relative)
                    result.append(_metadata(target, root, space))
                except (ImageManagerError, OSError) as error:
                    errors.append({'path': target.relative_to(root).as_posix(), 'error': str(error)})
        return result, errors

    def _save_plan(self, root, device, candidates, errors, *, direction='inbox', device_metadata=None):
        if len(candidates) > 1000:
            raise ImageManagerError('待确认图片超过 1000 张，请分批处理。')
        plan_id = uuid.uuid4().hex
        plan = {'id': plan_id, 'planId': plan_id, 'root': str(root), 'rootIdentity': _identity(root),
                'deviceRoot': str(device) if device else '', 'deviceIdentity': _identity(device) if device else None,
                'createdAt': _now(), 'direction': direction, 'candidates': candidates, 'errors': errors,
                'status': 'review', 'counts': {value: sum(c['status'] == value for c in candidates)
                                            for value in ('new', 'duplicate', 'conflict', 'ambiguous')}}
        if device_metadata is not None:
            plan['deviceMetadata'] = device_metadata
        _atomic_json(_inside(root, META + '/plans/' + plan_id + '.json', private=True), plan)
        _atomic_json(_inside(root, META + '/latest-plan.json', private=True), {'planId': plan_id})
        return plan

    def _candidate(self, incoming, existing, *, target_space='root'):
        matches = [entry for entry in existing if _same(incoming, entry)]
        exact = [entry for entry in matches if _same(incoming, entry) in {'bytes', 'pixels'}]
        if exact:
            matches = exact
        status = 'new' if not matches else ('ambiguous' if len(matches) > 1 else ('duplicate' if exact else 'conflict'))
        target = matches[0]['path'] if len(matches) == 1 else incoming['canonicalName']
        if len(matches) == 1:
            target = str(Path(target).with_suffix(Path(incoming['canonicalName']).suffix)).replace('\\', '/')
        return {'id': uuid.uuid4().hex, 'status': status, 'source': incoming['path'],
                'target': target,
                'targetSpace': target_space, 'incoming': incoming, 'existing': matches[0] if len(matches) == 1 else None,
                'matches': matches[:3], 'matchCount': len(matches), 'matchReason': _same(incoming, matches[0]) if matches else '',
                'suggestedAction': 'add' if not matches else 'keep',
                'actions': ['keep', 'add'] if len(matches) > 1 else ['keep', 'add', 'replace'] if matches else ['keep', 'add']}

    def scan(self, payload):
        config, root, device = self._roots(payload.get('expectedRoot'))
        with self._locked(root):
            previous = self._manifest(root)
            current, errors = self._files(root)
            pending, incoming_errors = self._files(root, inbox=True)
            self._inherit_path_annotations(current + pending, self._previous_annotation_items(root, previous), previous['annotations'])
            self._enrich(current + pending, previous['annotations'])
            retained = set(previous.get('retainedPairs', []))
            candidates, seen = [], []
            for entry in current:
                matches = [other for other in seen if _same(entry, other) and self._pair(entry, other) not in retained]
                if matches:
                    candidates.append(self._candidate(entry, matches))
                seen.append(entry)
            pool = list(current)
            for entry in pending:
                candidate = self._candidate(entry, pool)
                if candidate['matches'] and all(self._pair(entry, other) in retained for other in candidate['matches']):
                    continue
                if any(other['path'].split('/')[0].casefold() == 'inbox' for other in candidate['matches']):
                    candidate['actions'] = ['keep', 'add']
                    candidate['target'] = entry['canonicalName']
                candidates.append(candidate)
                pool.append(entry)
            previous['items'] = current
            _atomic_json(_inside(root, META + '/library.json', private=True), previous)
            result = self._save_plan(root, device, candidates, errors + incoming_errors)
            result['state'] = self.state()
            return result

    @staticmethod
    def _pair(left, right):
        return '|'.join(sorted([left['sha256'], right['sha256']]))

    def import_files(self, files, payload):
        config, root, device = self._roots(payload.get('expectedRoot'))
        if not isinstance(files, (list, tuple)) or not 1 <= len(files) <= 50:
            raise ImageManagerError('每批请选择 1 至 50 张图片。')
        with self._locked(root):
            batch = uuid.uuid4().hex
            directory = _inside(root, META + '/uploads/' + batch, private=True)
            directory.mkdir(parents=True)
            prepared = []
            try:
                total = 0
                for index, pair in enumerate(files):
                    name, data = pair
                    if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
                        raise ImageManagerError('上传图片名称无效。')
                    if not isinstance(data, bytes) or len(data) > MAX_IMAGE_BYTES:
                        raise ImageManagerError('上传图片超过单张 64 MiB 限制。')
                    total += len(data)
                    if total > 96 * 1024 * 1024:
                        raise ImageManagerError('每批上传总量不能超过 96 MiB。')
                    path = directory / (str(index) + Path(name).suffix.lower())
                    path.write_bytes(data)
                    metadata = _metadata(path, directory)
                    metadata['title'] = _title(name)
                    metadata['canonicalName'] = f"{metadata['title']} - {metadata['width']}x{metadata['height']}{Path(metadata['canonicalName']).suffix}"
                    prepared.append((path, metadata['canonicalName']))
                for path, name in prepared:
                    destination_directory = _inside(root, 'inbox/' + batch)
                    destination_directory.mkdir(exist_ok=True)
                    destination = self._available(destination_directory, name)
                    shutil.copy2(path, destination)
            finally:
                shutil.rmtree(directory)
        return self.scan({'expectedRoot': str(root)})

    def _available(self, directory, name, reserved=None):
        reserved = reserved if reserved is not None else set()
        suffix = Path(name).suffix
        stem = Path(name).stem
        candidate = directory / name
        number = 2
        while candidate.exists() or str(candidate).casefold() in reserved:
            candidate = directory / f'{stem} ({number}){suffix}'
            number += 1
        reserved.add(str(candidate).casefold())
        return candidate

    def image(self, path, expectedRoot=None, space='root'):
        config, root, device = self._roots(expectedRoot)
        directory = root if space == 'root' else device if space == 'device' else None
        if directory is None:
            raise ImageManagerError('图片位置无效。')
        target = _inside(directory, path)
        if not target.is_file() or target.suffix.lower() not in EXTENSIONS or target.stat().st_size > MAX_IMAGE_BYTES:
            raise ImageManagerError('图片不存在或格式不受支持。', status=404)
        try:
            with Image.open(target) as image:
                mime = Image.MIME.get(image.format, 'application/octet-stream')
        except (OSError, ValueError) as error:
            raise ImageManagerError('图片格式无法读取。') from error
        return {'path': target, 'name': target.name, 'mimeType': mime}

    def sync_device(self, payload):
        if payload.get('planId'):
            return self.apply(payload)
        config, root, device = self._roots(payload.get('expectedRoot'))
        if device is None:
            raise ImageManagerError('请先选择设备目标文件夹。')
        direction = payload.get('direction', 'to-device')
        if direction not in {'to-device', 'from-device'}:
            raise ImageManagerError('设备同步方向无效。')
        with self._locked(root), self._locked(device):
            versions = [(directory, self._manifest_version(directory), _identity(directory)) for directory in (root, device)]
            manifest = self._manifest(root)
            device_manifest = self._manifest(device)
            local, local_errors = self._files(root)
            remote, remote_errors = self._files(device)
            for directory, current, catalogue in ((root, manifest, local), (device, device_manifest, remote)):
                self._inherit_path_annotations(catalogue, self._previous_annotation_items(directory, current), current['annotations'])
                self._enrich(catalogue, current['annotations'])
            remote_view = json.loads(json.dumps(remote))
            for entry in remote_view:
                entry['space'] = 'device'
                entry['id'] = hashlib.sha256(('device:' + entry['path']).encode()).hexdigest()[:24]
                entry['previewUrl'] = '/api/images/preview?' + urlencode({'path': entry['path'], 'expectedRoot': str(root), 'space': 'device'})
            source, destination = (local, remote_view) if direction == 'to-device' else (remote_view, local)
            target_manifest, target_catalogue = (device_manifest, remote) if direction == 'to-device' else (manifest, local)
            destination_hashes = {item['sha256'] for item in destination}
            entries = [self._device_entry(item) for item in source]
            entries = list({entry['sha256']:entry for entry in entries}.values())
            matching = [entry for entry in entries if entry['sha256'] in destination_hashes]
            summary = self._merge_device_annotations(target_manifest, target_catalogue, matching)
            candidates = []
            for entry in source:
                candidate = self._candidate(entry, destination, target_space='device' if direction == 'to-device' else 'root')
                # Only identical originals can receive metadata without a file
                # decision. Equal pixels in another format still have a distinct
                # asset SHA and must not silently borrow the other's annotations.
                if entry['sha256'] not in destination_hashes:
                    candidates.append(candidate)
            self._device_guard(root, device, versions,
                [(item, root) for item in local] + [(item, device) for item in remote])
            manifest['items'] = local
            _atomic_json(_inside(root, META + '/library.json', private=True), manifest)
            versions[0] = (root, self._saved_manifest_version(root, manifest), versions[0][2])
            if direction == 'to-device' and matching:
                self._device_guard(root, device, versions,
                    [(item, root) for item in local] + [(item, device) for item in remote])
                _atomic_json(_inside(device, META + '/library.json', private=True), device_manifest)
                versions[1] = (device, self._saved_manifest_version(device, device_manifest), versions[1][2])
            self._device_guard(root, device, versions)
            context = {'rootVersion':versions[0][1], 'deviceVersion':versions[1][1],
                       'entries':entries}
            result = self._save_plan(root, device, candidates, local_errors + remote_errors,
                                     direction=direction, device_metadata=context)
            result['metadataSync'] = {**summary, 'notSynced':len(entries) - len(matching),
                                     'target':'device' if direction == 'to-device' else 'console',
                                     'status':'needs_review' if candidates or local_errors or remote_errors or summary['unresolved'] else 'completed'}
            result['message'] = (f"已同步 {summary['applied']} 项既有原图的方案信息。"
                                 + ('新图或差异仍待确认。' if candidates else '')
                                 + ('部分派生来源尚未同步，已保留待关联关系。' if summary['unresolved'] else '')
                                 + ('部分图片未能读取，同步尚未完整完成。' if local_errors or remote_errors else ''))
            return result

    def _fresh(self, metadata, roots):
        directory = roots.get(metadata.get('space', 'root'))
        if directory is None:
            raise ImageManagerError('同步文件夹配置已改变。', status=409)
        path = _inside(directory, metadata['path'])
        if (not path.is_file() or path.stat().st_size != metadata['size']
                or _sha(path) != metadata['sha256']):
            raise ImageManagerError('预览后图片已改变，请重新检查。', status=409)
        return path

    def apply(self, payload):
        config, root, device = self._roots(payload.get('expectedRoot'))
        plan_id = payload.get('planId', '')
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{32}', plan_id):
            raise ImageManagerError('图片操作计划无效。')
        with self._locked(root):
            if device:
                with self._locked(device):
                    return self._apply_locked(payload, root, device, plan_id)
            return self._apply_locked(payload, root, device, plan_id)

    def _apply_locked(self, payload, root, device, plan_id):
        plan_path = _inside(root, META + '/plans/' + plan_id + '.json', private=True)
        plan = _json(plan_path, None)
        if not isinstance(plan, dict):
            raise ImageManagerError('找不到图片操作计划。', status=404)
        roots = {'root': root, 'device': device}
        if (plan['root'] != str(root) or plan['rootIdentity'] != _identity(root)
                or plan['deviceRoot'] != (str(device) if device else '')
                or plan['deviceIdentity'] != (_identity(device) if device else None)):
            raise ImageManagerError('同步目标已改变，请重新检查。', status=409)
        decisions = payload.get('decisions', [])
        if not isinstance(decisions, list):
            raise ImageManagerError('请选择每张候选图片的处理方式。')
        choices = {}
        for value in decisions:
            if not isinstance(value, dict) or set(value) != {'id', 'action'} or value['id'] in choices:
                raise ImageManagerError('图片处理选择无效或重复。')
            choices[value['id']] = value['action']
        decision_hash = hashlib.sha256(json.dumps(sorted(choices.items())).encode()).hexdigest()
        if plan['status'] == 'completed':
            recovery = _json(_inside(root, META + '/history/' + plan_id + '/recovery.json', private=True), {})
            if recovery.get('status') != 'completed':
                raise ImageManagerError('此计划的回执与恢复记录不一致，请先核对图片。', status=409)
            if plan.get('decisionHash') != decision_hash:
                raise ImageManagerError('此计划已按其他选择完成，请重新检查。', status=409)
            return {**plan['receipt'], 'replayed': True, 'state': self.state()}
        if plan['status'] != 'review':
            raise ImageManagerError('此计划仍有待核对的恢复记录，请先检查。', status=409)
        if set(choices) != {value['id'] for value in plan['candidates']}:
            raise ImageManagerError('请确认全部候选图片后再应用。')
        manifest = self._manifest(root)
        original_manifest = json.loads(json.dumps(manifest))
        device_context = plan.get('deviceMetadata')
        device_versions = []
        original_device_manifest = device_written_version = None
        device_write_attempted = False
        root_write_attempted = False
        root_written_version = None
        if device_context is not None:
            device_versions = [(root, device_context['rootVersion'], plan['rootIdentity']),
                               (device, device_context['deviceVersion'], plan['deviceIdentity'])]
            self._device_guard(root, device, device_versions)
            original_device_manifest = self._manifest(device)
        self._enrich(manifest['items'] + [item for item in self._plan_items(plan)
                     if item.get('space', 'root') == 'root'], manifest['annotations'])
        retained = set(manifest.get('retainedPairs', []))
        operations, touched, reserved = [], set(), set()
        for candidate in plan['candidates']:
            action = choices[candidate['id']]
            if action not in candidate['actions']:
                raise ImageManagerError('这张图片不支持所选处理方式。')
            incoming = candidate['incoming']
            source = self._fresh(incoming, roots)
            existing = candidate['existing']
            previous = self._fresh(existing, roots) if existing else None
            if action == 'keep':
                for matching in candidate['matches']:
                    retained.add(self._pair(incoming, matching))
                # Keep is intentionally non-destructive: the inbox source remains,
                # with its pair acknowledged to avoid presenting it again.
                operations.append({'action': 'keep', 'source': source, 'candidate': candidate})
                continue
            target_root = roots[candidate['targetSpace']]
            if action == 'replace':
                if previous is None:
                    raise ImageManagerError('没有唯一替换目标，请另存或保留。')
                if device_context is None and not incoming.get('variantExplicit') and existing['sha256'] in manifest['annotations']:
                    manifest['annotations'][incoming['sha256']] = self._inherit_annotation(manifest['annotations'][existing['sha256']])
                target = previous.with_suffix(Path(incoming['canonicalName']).suffix)
                if target != previous and target != source and target.exists():
                    raise ImageManagerError('新格式的目标文件已经存在，请选择另存或分批处理。', status=409)
            else:
                target = self._available(target_root, incoming['canonicalName'], reserved)
                for matching in manifest['items'] + candidate['matches']:
                    if matching['sha256'] != incoming['sha256'] and _same(incoming, matching):
                        retained.add(self._pair(incoming, matching))
            # One file may not be replaced twice by a single confirmation.
            key = str(target).casefold()
            if key in touched:
                raise ImageManagerError('多张图片要替换同一目标，请分批确认。', status=409)
            touched.add(key)
            operations.append({'action': action, 'source': source, 'target': target, 'previous': previous,
                               'candidate': candidate})
        transaction = _inside(root, META + '/history/' + plan_id, private=True)
        transaction.mkdir(parents=True, exist_ok=True)
        journal = {'planId': plan_id, 'startedAt': _now(), 'status': 'prepared', 'files': []}
        _atomic_json(transaction / 'catalogue-before.json', original_manifest)
        if device_context is not None:
            _atomic_json(transaction / 'device-catalogue-before.json', original_device_manifest)
        # Snapshot all write targets and sources before the first mutation.
        backups = {}
        expected = {}
        for operation in operations:
            if operation['action'] == 'keep':
                continue
            expected[operation['source']] = operation['candidate']['incoming']['sha256']
            expected[operation['target']] = (operation['candidate']['incoming']['sha256'] if operation['target'] == operation['source'] else
                                             operation['candidate']['existing']['sha256']
                                             if operation['action'] == 'replace' and operation['target'] == operation['previous'] else None)
            if operation['previous'] is not None:
                expected[operation['previous']] = operation['candidate']['existing']['sha256']
        for operation in operations:
            if operation['action'] == 'keep':
                continue
            for original in (operation['source'], operation['target'], operation['previous']):
                if original is None:
                    continue
                if original in backups:
                    continue
                backup = transaction / (str(len(backups)) + original.suffix)
                existed = original.exists()
                if (expected.get(original) is None and existed) or (expected.get(original) is not None and (
                        not existed or _sha(original) != expected[original])):
                    raise ImageManagerError('准备期间图片已改变，请重新检查。', status=409)
                if existed:
                    shutil.copy2(original, backup)
                    if _sha(backup) != expected[original] or _sha(original) != expected[original]:
                        raise ImageManagerError('备份期间图片已改变，请重新检查。', status=409)
                backups[original] = (backup, existed)
                journal['files'].append({'original': str(original), 'backup': backup.name, 'existed': existed,
                                         'beforeSha256': expected[original]})
        for entry in journal['files']:
            original = Path(entry['original'])
            entry['afterSha256'] = entry['beforeSha256']
            for operation in operations:
                if operation['action'] == 'keep':
                    continue
                candidate = operation['candidate']
                if original == operation['target']:
                    entry['afterSha256'] = candidate['incoming']['sha256']
                if (original == operation['source'] and candidate['incoming']['space'] == 'root'
                        and plan['direction'] == 'inbox' and original != operation['target']):
                    entry['afterSha256'] = None
                if operation['action'] == 'replace' and original == operation['previous'] and original != operation['target']:
                    entry['afterSha256'] = None
        _atomic_json(transaction / 'recovery.json', journal)
        completed = []
        mutated = {}
        try:
            for operation in operations:
                if operation['action'] == 'keep':
                    continue
                source, target = operation['source'], operation['target']
                candidate = operation['candidate']
                # Verify source and target again at the actual write boundary.
                self._fresh(candidate['incoming'], roots)
                if operation['action'] == 'replace':
                    self._fresh(candidate['existing'], roots)
                elif target.exists():
                    raise ImageManagerError('目标出现新文件，请重新检查。', status=409)
                temporary = target.with_name('.image-import-' + uuid.uuid4().hex + target.suffix)
                try:
                    shutil.copy2(backups[source][0], temporary)
                    if _sha(temporary) != candidate['incoming']['sha256']:
                        raise ImageManagerError('复制后原图校验失败。', status=409)
                    os.replace(temporary, target)
                    mutated[target] = candidate['incoming']['sha256']
                finally:
                    temporary.unlink(missing_ok=True)
                # Retain source in history and consume only inbox or a root
                # duplicate explicitly replaced; device exports keep their source.
                consume = (candidate['incoming']['space'] == 'root'
                           and plan['direction'] == 'inbox' and source != target)
                if consume:
                    source.unlink()
                    mutated[source] = None
                if operation['action'] == 'replace' and operation['previous'] != target:
                    self._fresh(candidate['existing'], roots)
                    operation['previous'].unlink()
                    mutated[operation['previous']] = None
                completed.append({'id': candidate['id'], 'action': operation['action'],
                                  'target': str(target), 'sha256': candidate['incoming']['sha256']})
            current, errors = self._files(root)
            metadata_summary = None
            if device_context is not None:
                self._device_guard(root, device, device_versions)
                if plan['direction'] == 'to-device':
                    target_items, target_errors = self._files(device)
                    target_manifest = json.loads(json.dumps(original_device_manifest))
                else:
                    target_items, target_errors, target_manifest = current, errors, manifest
                if target_errors:
                    raise ImageManagerError('设备同步后的原图无法完整核验，未完成方案同步。', status=409)
                present = {item['sha256'] for item in target_items}
                entries = [entry for entry in device_context['entries'] if entry['sha256'] in present]
                metadata_summary = self._merge_device_annotations(target_manifest, target_items, entries)
                metadata_summary['notSynced'] = len(device_context['entries']) - len(entries)
                metadata_summary.update(target='device' if plan['direction'] == 'to-device' else 'console',
                    status='needs_review' if metadata_summary['unresolved'] or metadata_summary['notSynced'] or plan.get('errors') else 'completed')
                self._device_guard(root, device, device_versions,
                    [(item, device if plan['direction'] == 'to-device' else root) for item in target_items])
                if plan['direction'] == 'to-device' and entries:
                    device_write_attempted = True
                    _atomic_json(_inside(device, META + '/library.json', private=True), target_manifest)
                    device_written_version = self._saved_manifest_version(device, target_manifest)
            self._enrich(current, manifest['annotations'])
            manifest['items'] = current
            manifest['retainedPairs'] = sorted(retained)
            manifest['lastSync'] = {'at': _now(), 'direction': plan['direction'], 'applied': len(completed), 'planId': plan_id}
            if device_context is not None:
                self._device_guard(root, device, [device_versions[0]])
                root_write_attempted = True
            _atomic_json(_inside(root, META + '/library.json', private=True), manifest)
            if device_context is not None:
                root_written_version = self._saved_manifest_version(root, manifest)
            receipt = {'ok': True, 'planId': plan_id, 'applied': len(completed), 'kept': len(operations) - len(completed),
                       'results': completed, 'historyPath': str(transaction), 'completedAt': _now(), 'errors': errors}
            if metadata_summary is not None:
                receipt['metadataSync'] = metadata_summary
            journal['status'] = 'completed'
            _atomic_json(transaction / 'recovery.json', journal)
            final_state = self.state()
            if (final_state.get('plan') or {}).get('id') == plan_id:
                final_state['plan'] = None
            # The durable receipt is the final commit point. Do not perform
            # further fallible reads/writes after recording completion.
            plan.update(status='completed', decisionHash=decision_hash, receipt=receipt)
            _atomic_json(plan_path, plan)
            return {**receipt, 'state': final_state}
        except Exception:
            failures = []
            if device_write_attempted:
                try:
                    actual = self._manifest_version(device)
                    if device_written_version is None and actual == device_context['deviceVersion']:
                        pass  # The attempted atomic write did not change the target.
                    elif device_written_version is None or actual != device_written_version:
                        raise ImageManagerError('设备方案信息已有后续更改。', status=409)
                    else:
                        self._device_guard(root, device, [(device, actual, plan['deviceIdentity'])])
                        if device_context['deviceVersion'] is None:
                            _inside(device, META + '/library.json', private=True).unlink()
                        else:
                            _atomic_json(_inside(device, META + '/library.json', private=True), original_device_manifest)
                except (OSError, ImageManagerError):
                    failures.append('device catalogue')
            for original, last_written in reversed(list(mutated.items())):
                backup, existed = backups[original]
                try:
                    if ((last_written is None and original.exists()) or (last_written is not None and (
                            not original.is_file() or _sha(original) != last_written))):
                        failures.append(str(original))
                        continue
                    if existed:
                        shutil.copy2(backup, original)
                    else:
                        original.unlink(missing_ok=True)
                except OSError:
                    failures.append(str(original))
            journal['status'] = 'recovery_required' if failures else 'rolled_back'
            journal['failedPaths'] = failures
            _atomic_json(transaction / 'recovery.json', journal)
            try:
                if device_context is None:
                    _atomic_json(_inside(root, META + '/library.json', private=True), original_manifest)
                else:
                    actual = self._manifest_version(root)
                    if actual == device_context['rootVersion']:
                        pass  # No root catalogue mutation needs undoing.
                    elif not root_write_attempted or root_written_version is None or actual != root_written_version:
                        raise ImageManagerError('本地方案已有后续修改，回滚不会覆盖。', status=409)
                    else:
                        self._device_guard(root, device, [(root, actual, plan['rootIdentity'])])
                        _atomic_json(_inside(root, META + '/library.json', private=True), original_manifest)
            except (OSError, ImageManagerError):
                journal['status'] = 'recovery_required'
                _atomic_json(transaction / 'recovery.json', journal)
                failures.append('catalogue')
            plan['status'] = 'recovery_required' if failures else 'review'
            plan.pop('receipt', None)
            plan.pop('decisionHash', None)
            try:
                _atomic_json(plan_path, plan)
            except OSError:
                # A completed receipt may not be replayed against a rolled-back
                # journal even if the disk cannot save this corrected plan.
                pass
            raise

    def restore(self, payload):
        """Undo a reviewed transaction, preserving any subsequent user edits."""
        config, root, device = self._roots(payload.get('expectedRoot'))
        plan_id = payload.get('planId', '')
        if not isinstance(plan_id, str) or not re.fullmatch(r'[0-9a-f]{32}', plan_id):
            raise ImageManagerError('恢复计划无效。')
        with self._locked(root):
            if device:
                with self._locked(device):
                    return self._restore_locked(root, device, plan_id)
            return self._restore_locked(root, device, plan_id)

    def _restore_locked(self, root, device, plan_id):
        plan_path = _inside(root, META + '/plans/' + plan_id + '.json', private=True)
        plan = _json(plan_path, {})
        if (plan.get('root') != str(root) or plan.get('rootIdentity') != _identity(root)
                or plan.get('deviceRoot') != (str(device) if device else '')
                or plan.get('deviceIdentity') != (_identity(device) if device else None)):
            raise ImageManagerError('恢复目标配置或文件夹身份已改变。', status=409)
        directory = _inside(root, META + '/history/' + plan_id, private=True)
        journal = _json(directory / 'recovery.json', {})
        if journal.get('status') == 'restored':
            return {'ok': True, 'planId': plan_id, 'restored': True, 'replayed': True, 'state': self.state()}
        if journal.get('status') not in {'completed', 'prepared', 'recovery_required'}:
            raise ImageManagerError('此记录没有待恢复的图片变更。', status=409)
        prepared = []
        for entry in journal.get('files', []):
            original = Path(entry['original'])
            matched_root = next((value for value in (root, device) if value is not None and original.is_relative_to(value)), None)
            if matched_root is None:
                raise ImageManagerError('恢复记录包含图库以外的路径。', status=409)
            original = _inside(matched_root, original.relative_to(matched_root).as_posix())
            backup = _inside(root, META + '/history/' + plan_id + '/' + entry['backup'], private=True)
            before, after = entry['beforeSha256'], entry['afterSha256']
            current = _sha(original) if original.is_file() else None
            if current not in {before, after}:
                raise ImageManagerError('图片在操作后又被修改，恢复不会覆盖这些修改。', status=409)
            if before is not None and (not backup.is_file() or _sha(backup) != before):
                raise ImageManagerError('恢复备份校验失败，原图保持不变。', status=409)
            prepared.append((original, backup, before, current))
        # All paths and all original bytes pass before the first restoration.
        for original, backup, before, expected in reversed(prepared):
            current = _sha(original) if original.is_file() else None
            if current != expected:
                raise ImageManagerError('恢复期间图片有新改动，请重新核对。', status=409)
            if before is None:
                original.unlink(missing_ok=True)
            else:
                temporary = original.with_name('.image-restore-' + uuid.uuid4().hex + original.suffix)
                try:
                    shutil.copy2(backup, temporary)
                    os.replace(temporary, original)
                finally:
                    temporary.unlink(missing_ok=True)
        current_annotations = self._manifest(root)['annotations']
        before_manifest = _json(directory / 'catalogue-before.json', {'items': [], 'retainedPairs': []})
        before_manifest['annotations'] = {**before_manifest.get('annotations', {}), **current_annotations}
        before_manifest['items'], errors = self._files(root)
        self._enrich(before_manifest['items'], before_manifest['annotations'])
        _atomic_json(_inside(root, META + '/library.json', private=True), before_manifest)
        if plan.get('deviceMetadata') is not None and plan['direction'] == 'to-device':
            version = self._manifest_version(device)
            device_manifest = self._manifest(device)
            device_manifest['items'], device_errors = self._files(device)
            self._enrich(device_manifest['items'], device_manifest['annotations'])
            self._device_guard(root, device, [(device, version, plan['deviceIdentity'])])
            _atomic_json(_inside(device, META + '/library.json', private=True), device_manifest)
            errors += device_errors
        journal['status'] = 'restored'
        journal['restoredAt'] = _now()
        _atomic_json(directory / 'recovery.json', journal)
        plan['status'] = 'restored'
        _atomic_json(plan_path, plan)
        return {'ok': True, 'planId': plan_id, 'restored': True, 'errors': errors, 'state': self.state()}
