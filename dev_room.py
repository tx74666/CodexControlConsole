"""Small editable Dev Room document collection in the selected document library."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid


DEV_ROOM_PARTS = ('projects', 'Project Nexus', 'Dev Room')
MAX_TITLE_CHARS = 200
MAX_BODY_BYTES = 512 * 1024
MAX_HEADER_BYTES = 4096
MAX_DOCUMENTS = 500
MAX_REQUEST_BYTES = MAX_BODY_BYTES * 6 + MAX_HEADER_BYTES
MAX_LOCALE_BYTES = MAX_BODY_BYTES * 2 + MAX_HEADER_BYTES * 2
MAX_CATALOG_BYTES = 8 * 1024 * 1024
_HEADER_PREFIX = '<!-- codex-dev-room '
_HEADER_SUFFIX = ' -->'


class DevRoomConflict(ValueError):
    """The caller's document revision is no longer current."""


class DevRoomService:
    def __init__(self, document_library, translations_path=None):
        self.library = document_library
        self.translations_path = Path(translations_path) if translations_path is not None else Path(__file__).with_name('dev-room-translations.json')

    @staticmethod
    def _language(value):
        if value not in ('zh', 'en') or not isinstance(value, str):
            raise ValueError('Dev Room 语言仅支持 zh 或 en。')
        return value

    @staticmethod
    def _json(raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Dev Room 语言文件包含重复字段。')
                result[key] = value
            return result
        try:
            return json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        except (UnicodeError, ValueError) as exc:
            raise ValueError('Dev Room 语言文件格式有误，原文件已保留。') from exc

    def _variants(self, value):
        if not isinstance(value, dict) or set(value) - {'zh', 'en'}:
            raise ValueError('Dev Room 语言版本无效。')
        for language, variant in value.items():
            self._language(language)
            if not isinstance(variant, dict) or set(variant) != {'title', 'body'}:
                raise ValueError('Dev Room 语言版本字段无效。')
            self._title(variant['title'])
            self._body(variant['body'])
        return value

    @staticmethod
    def _structure(source, translated):
        marker = r'<!-- rr-dev-room:[\s\S]*?-->'
        if re.findall(marker, source) != re.findall(marker, translated):
            raise ValueError('Dev Room 来源身份和章节标识不能修改。')

    def _catalog(self):
        path = self.translations_path
        if not path.exists():
            return {}
        for component in (path, *path.parents):
            if component.is_symlink() or getattr(component.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Dev Room 内置语言文件含文件链接。')
        with path.open('rb') as source:
            raw = source.read(MAX_CATALOG_BYTES + 1)
        if len(raw) > MAX_CATALOG_BYTES:
            raise ValueError('Dev Room 内置语言文件超过读取限制。')
        catalog = self._json(raw)
        if (not isinstance(catalog, dict) or set(catalog) != {'version', 'documents'}
                or type(catalog['version']) is not int or catalog['version'] != 1
                or not isinstance(catalog['documents'], list) or len(catalog['documents']) > MAX_DOCUMENTS):
            raise ValueError('Dev Room 内置语言目录无效。')
        result = {}
        for entry in catalog['documents']:
            if not isinstance(entry, dict) or set(entry) != {'id', 'sourceTitle', 'sourceBodySha256', 'variants'}:
                raise ValueError('Dev Room 内置语言目录字段无效。')
            identifier = self._id(entry['id'])
            if identifier in result or not isinstance(entry['sourceBodySha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', entry['sourceBodySha256']):
                raise ValueError('Dev Room 内置语言来源无效。')
            self._title(entry['sourceTitle'])
            self._variants(entry['variants'])
            result[identifier] = entry
        return result

    def _locale_raw(self, root, identifier):
        path = self._checked_path(root, *DEV_ROOM_PARTS, '.locales', identifier + '.json')
        if not path.exists():
            return None, ''
        if not path.is_file():
            raise ValueError('Dev Room 语言文件不是普通文件。')
        with path.open('rb') as source:
            raw = source.read(MAX_LOCALE_BYTES + 1)
        return raw, self._updated_at(path.stat())

    def _locale(self, raw, identifier):
        if raw is None:
            return None
        if len(raw) > MAX_LOCALE_BYTES:
            raise ValueError('Dev Room 语言文件超过读取限制。')
        value = self._json(raw)
        required = {'version', 'id', 'sourceRevision', 'variants'}
        if (not isinstance(value, dict) or set(value) - (required | {'sourceLanguage'}) or not required <= set(value)
                or type(value['version']) is not int or value['version'] != 1 or value['id'] != identifier
                or not isinstance(value['sourceRevision'], str) or not re.fullmatch(r'[0-9a-f]{64}', value['sourceRevision'])):
            raise ValueError('Dev Room 语言文件身份或来源无效。')
        self._id(value['id'])
        self._variants(value['variants'])
        if 'sourceLanguage' in value:
            self._language(value['sourceLanguage'])
        return value

    @staticmethod
    def _matched_catalog(current, catalog):
        entry = catalog.get(current['id']) if current else None
        if (entry and current['revision'] and current['title'] == entry['sourceTitle']
                and hashlib.sha256(current['body'].encode('utf-8')).hexdigest() == entry['sourceBodySha256']):
            return entry
        return None

    @staticmethod
    def _locale_revision(current, raw, entry):
        if (not current or not current['revision']) and raw is None:
            return ''
        fields = [(current['revision'] if current else '').encode('ascii'), raw or b'',
                  json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8') if entry else b'']
        digest = hashlib.sha256(b'codex-dev-room-locales-v1\0')
        for field in fields:
            digest.update(len(field).to_bytes(8, 'big'))
            digest.update(field)
        return digest.hexdigest()

    def _localized(self, root, current, language, catalog):
        if current is None:
            return None
        raw, updated_at = self._locale_raw(root, current['id'])
        locale = self._locale(raw, current['id'])
        entry = self._matched_catalog(current, catalog)
        valid = locale and locale['sourceRevision'] == current['revision']
        for variant in (locale['variants'].values() if valid else ()):
            self._structure(current['body'], variant['body'])
        for variant in (entry['variants'].values() if entry else ()):
            self._structure(current['body'], variant['body'])
        variant = locale['variants'].get(language) if valid else None
        if variant is None and entry:
            variant = entry['variants'].get(language)
        if variant is None and valid and locale.get('sourceLanguage') == language:
            variant = {'title': current['title'], 'body': current['body']}
        virtual = not current['revision'] and current['id'] == 'overview'
        if variant:
            self._structure(current['body'], variant['body'])
        title = variant['title'] if variant else ('总案' if language == 'zh' else 'Overview') if virtual else ('待翻译文档' if language == 'zh' else 'Translation needed')
        return {'id': current['id'], 'title': title, 'body': variant['body'] if variant else '',
                'revision': self._locale_revision(current, raw, entry),
                'updatedAt': updated_at if variant and valid and language in locale['variants'] else current['updatedAt'],
                'language': language, 'sourceRevision': current['revision'], 'sourceBody': current['body'],
                'translationMissing': not variant and not virtual}

    def _state_localized(self, root, identifier, language, catalog=None):
        catalog = self._catalog() if catalog is None else catalog
        summaries, selected = [], None
        for summary in self._summaries(root):
            current = self._read(root, summary['id'])[0]
            document = self._localized(root, current, language, catalog)
            if document is None:
                continue
            summaries.append({key: document[key] for key in ('id', 'title', 'updatedAt', 'language', 'translationMissing')})
            if summary['id'] == identifier:
                selected = document
        self._check_current_root(root)
        return {'root': str(root), 'documents': summaries, 'document': selected}

    @staticmethod
    def _id(value):
        if value == 'overview':
            return value
        if not isinstance(value, str) or len(value) != 36:
            raise ValueError('Dev Room 文档身份无效。')
        try:
            if str(uuid.UUID(value)) != value:
                raise ValueError()
        except ValueError as exc:
            raise ValueError('Dev Room 文档身份无效。') from exc
        return value

    @staticmethod
    def _title(value):
        if (not isinstance(value, str) or not value.strip() or len(value) > MAX_TITLE_CHARS
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError('请输入不超过 200 字的文档标题。')
        try:
            value.encode('utf-8')
        except UnicodeError as exc:
            raise ValueError('文档标题包含无效文字。') from exc
        return value

    @staticmethod
    def _body(value):
        if not isinstance(value, str) or '\0' in value:
            raise ValueError('文档正文无效。')
        try:
            if len(value.encode('utf-8')) > MAX_BODY_BYTES:
                raise ValueError('文档正文超过 512 KiB，请分成多份文档。')
        except UnicodeError as exc:
            raise ValueError('文档正文包含无效文字。') from exc
        return value

    @staticmethod
    def _checked_path(root, *parts):
        """Reject links/reparse points at every component, including missing targets."""
        current = root
        for part in (None, *parts):
            if part is not None:
                current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if current.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Dev Room 路径含文件链接，请先检查资料库。')
        if not current.resolve().is_relative_to(root):
            raise ValueError('Dev Room 路径不能离开所选资料库。')
        return current

    @classmethod
    def _mkdir(cls, root, *parts):
        for index in range(1, len(parts) + 1):
            path = cls._checked_path(root, *parts[:index])
            path.mkdir(exist_ok=True)
            cls._checked_path(root, *parts[:index])
        return cls._checked_path(root, *parts)

    def _selected_root(self):
        selected = self.library.state()
        configured = Path(selected.get('root') or '')
        if not selected.get('exists') or not configured.is_absolute():
            raise ValueError('Dev Room 资料库不存在，请重新打开。')
        # Inspect the configured spelling before resolving it: the selected
        # directory or an ancestor may have been replaced with a junction.
        for component in (configured, *configured.parents):
            info = component.lstat()
            if component.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Dev Room 资料库路径含文件链接，请先检查资料库。')
        return configured.resolve()

    def _check_current_root(self, root):
        # Do not use _root(): its scope pin deliberately masks later selection
        # changes. Re-read settings to detect a change by another Console process.
        if self._selected_root() != root:
            raise ValueError('资料库已切换，请重新打开 Dev Room 后保存。')

    @contextmanager
    def _scope(self, expectedRoot):
        if not isinstance(expectedRoot, str) or not expectedRoot.strip():
            raise ValueError('Dev Room 资料库路径无效，请重新打开。')
        with self.library._lock:
            selected = self._selected_root()
            with self.library._document_scope(expectedRoot) as root:
                if root != selected:
                    raise ValueError('资料库已切换，请重新打开 Dev Room。')
                self._checked_path(root)
                yield root

    @contextmanager
    def _write_lock(self, root):
        self._mkdir(root, *DEV_ROOM_PARTS)
        path = self._checked_path(root, *DEV_ROOM_PARTS, '.dev-room.lock')
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
                raise OSError('另一处正在保存 Dev Room 文档，请稍后重试。') from exc
            try:
                self._checked_path(root, *DEV_ROOM_PARTS, '.dev-room.lock')
                yield
            finally:
                lock_file.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _updated_at(info):
        return datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()

    def _metadata(self, header, id):
        try:
            line = header.decode('utf-8').removesuffix('\n')
            if not line.startswith(_HEADER_PREFIX) or not line.endswith(_HEADER_SUFFIX):
                raise ValueError()
            value = json.loads(line[len(_HEADER_PREFIX):-len(_HEADER_SUFFIX)])
            if (not isinstance(value, dict) or set(value) != {'version', 'id', 'title'}
                    or value['version'] != 1 or value['id'] != id):
                raise ValueError()
            return self._title(value['title'])
        except (UnicodeError, ValueError, KeyError) as exc:
            raise ValueError('Dev Room 文档格式有误，原文件已保留。') from exc

    def _summaries(self, root):
        directory = self._checked_path(root, *DEV_ROOM_PARTS)
        summaries = []
        if directory.exists():
            for entry in directory.iterdir():
                if entry.suffix != '.md':
                    continue
                try:
                    id = self._id(entry.stem)
                except ValueError:
                    continue
                path = self._checked_path(root, *DEV_ROOM_PARTS, entry.name)
                if not path.is_file():
                    raise ValueError('Dev Room 文档路径不是普通文件。')
                info = path.stat()
                if info.st_size > MAX_BODY_BYTES + MAX_HEADER_BYTES:
                    raise ValueError('Dev Room 文档超过读取限制，原文件已保留。')
                with path.open('rb') as source:
                    header = source.readline(MAX_HEADER_BYTES + 1)
                if len(header) > MAX_HEADER_BYTES or not header.endswith(b'\n'):
                    raise ValueError('Dev Room 文档标题格式有误，原文件已保留。')
                summaries.append({'id': id, 'title': self._metadata(header, id),
                                  'updatedAt': self._updated_at(info)})
                if len(summaries) > MAX_DOCUMENTS:
                    raise ValueError('Dev Room 文档数量超过读取限制。')
        if not any(item['id'] == 'overview' for item in summaries):
            summaries.append({'id': 'overview', 'title': '总案', 'updatedAt': ''})
        summaries.sort(key=lambda item: (item['updatedAt'], item['id']), reverse=True)
        summaries.sort(key=lambda item: item['id'] != 'overview')
        return summaries

    def _read(self, root, id):
        path = self._checked_path(root, *DEV_ROOM_PARTS, id + '.md')
        if not path.exists():
            if id == 'overview':
                return ({'id': id, 'title': '总案', 'body': '', 'revision': '', 'updatedAt': ''}, None)
            return None, None
        info = path.stat()
        with path.open('rb') as source:
            raw = source.read(MAX_BODY_BYTES + MAX_HEADER_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES + MAX_HEADER_BYTES:
            raise ValueError('Dev Room 文档超过读取限制，原文件已保留。')
        header, separator, body = raw.partition(b'\n')
        if not separator or len(header) + 1 > MAX_HEADER_BYTES:
            raise ValueError('Dev Room 文档格式有误，原文件已保留。')
        title = self._metadata(header, id)
        try:
            text = self._body(body.decode('utf-8'))
        except UnicodeError as exc:
            raise ValueError('Dev Room 文档编码有误，原文件已保留。') from exc
        return ({'id': id, 'title': title, 'body': text,
                 'revision': hashlib.sha256(raw).hexdigest(), 'updatedAt': self._updated_at(info)}, raw)

    def _state(self, root, id):
        result = {'root': str(root), 'documents': self._summaries(root), 'document': self._read(root, id)[0]}
        self._check_current_root(root)
        return result

    def state(self, expectedRoot, id='overview', language=None):
        id = self._id(id)
        if language is not None:
            language = self._language(language)
        with self._scope(expectedRoot) as root:
            return self._state(root, id) if language is None else self._state_localized(root, id, language)

    def _atomic_write(self, root, parts, content, before_replace=None):
        path = self._checked_path(root, *parts)
        temporary_parts = (*parts[:-1], '.' + parts[-1] + '.' + uuid.uuid4().hex + '.tmp')
        temporary = self._checked_path(root, *temporary_parts)
        try:
            with temporary.open('xb') as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            self._check_current_root(root)
            self._checked_path(root, *parts)
            self._checked_path(root, *temporary_parts)
            if before_replace is not None:
                before_replace()
            # Version checks may perform more reads. Recheck after the callback
            # so a directory swapped during those reads cannot redirect replace.
            self._check_current_root(root)
            self._checked_path(root, *parts)
            self._checked_path(root, *temporary_parts)
            os.replace(temporary, path)
        finally:
            # If a directory was replaced by a link meanwhile, never follow it
            # even when cleaning our own temporary filename.
            self._checked_path(root, *temporary_parts).unlink(missing_ok=True)

    def save(self, payload):
        if isinstance(payload, dict) and 'language' in payload:
            return self._save_localized(payload)
        required = {'expectedRoot', 'id', 'title', 'body', 'expectedRevision'}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError('Dev Room 保存请求无效。')
        id, title, body = self._id(payload['id']), self._title(payload['title']), self._body(payload['body'])
        expected = payload['expectedRevision']
        if not isinstance(expected, str) or expected and not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError('Dev Room 文档版本无效，请重新打开。')
        metadata = json.dumps({'version': 1, 'id': id, 'title': title}, ensure_ascii=False,
                              separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e')
        raw = (_HEADER_PREFIX + metadata + _HEADER_SUFFIX + '\n' + body).encode('utf-8')
        with self._scope(payload['expectedRoot']) as root, self._write_lock(root):
            self._check_current_root(root)
            current, old_raw = self._read(root, id)

            def require_revision():
                latest = self._read(root, id)[0]
                if (latest['revision'] if latest else '') != expected:
                    raise DevRoomConflict('这份文档已有更新，请保留当前草稿并重新读取后保存。')

            require_revision()
            summaries = self._summaries(root)
            if current is None and len(summaries) >= MAX_DOCUMENTS:
                raise ValueError('Dev Room 已达 500 份文档，请先整理现有文档。')
            if old_raw == raw:
                return self._state(root, id)
            if old_raw is not None:
                self._mkdir(root, *DEV_ROOM_PARTS, '.history', id)
                backup_parts = (*DEV_ROOM_PARTS, '.history', id, expected + '.md')
                backup = self._checked_path(root, *backup_parts)
                if backup.exists():
                    with backup.open('rb') as source:
                        stored = source.read(MAX_BODY_BYTES + MAX_HEADER_BYTES + 1)
                    if stored != old_raw:
                        raise ValueError('Dev Room 历史版本校验失败，原文件已保留。')
                else:
                    self._atomic_write(root, backup_parts, old_raw)
            self._atomic_write(root, (*DEV_ROOM_PARTS, id + '.md'), raw, before_replace=require_revision)
            return self._state(root, id)

    def _save_localized(self, payload):
        if set(payload) != {'expectedRoot', 'id', 'title', 'body', 'expectedRevision', 'language'}:
            raise ValueError('Dev Room 语言保存请求无效。')
        identifier, language = self._id(payload['id']), self._language(payload['language'])
        title, body = self._title(payload['title']), self._body(payload['body'])
        expected = payload['expectedRevision']
        if not isinstance(expected, str) or expected and not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError('Dev Room 语言版本无效，请重新打开。')
        with self._scope(payload['expectedRoot']) as root, self._write_lock(root):
            current, source_raw = self._read(root, identifier)
            locale_raw, _ = self._locale_raw(root, identifier)
            locale = self._locale(locale_raw, identifier)
            catalog = self._catalog()
            entry = self._matched_catalog(current, catalog)
            if self._locale_revision(current, locale_raw, entry) != expected:
                raise DevRoomConflict('文档来源或语言版本已有更新，请保留草稿并重新读取。')
            self._structure(current['body'] if current else '', body)
            creating = source_raw is None
            if creating and locale_raw is not None:
                raise DevRoomConflict('语言版本的原文缺失，请先核对原文，已有语言稿已保留。')
            if creating:
                if len(self._summaries(root)) >= MAX_DOCUMENTS:
                    raise ValueError('Dev Room 已达 500 份文档，请先整理现有文档。')
                metadata = json.dumps({'version': 1, 'id': identifier, 'title': title}, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e')
                new_source = (_HEADER_PREFIX + metadata + _HEADER_SUFFIX + '\n' + body).encode('utf-8')
                source_revision = hashlib.sha256(new_source).hexdigest()
            else:
                source_revision = current['revision']
            valid = locale and locale['sourceRevision'] == source_revision
            if valid:
                for variant in locale['variants'].values():
                    self._structure(current['body'], variant['body'])
            updated = {'version': 1, 'id': identifier, 'sourceRevision': source_revision,
                       'variants': dict(locale['variants']) if valid else {}}
            if valid and 'sourceLanguage' in locale:
                updated['sourceLanguage'] = locale['sourceLanguage']
            if creating:
                updated['sourceLanguage'] = language
            updated['variants'][language] = {'title': title, 'body': body}
            new_locale = json.dumps(updated, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8') + b'\n'
            if len(new_locale) > MAX_LOCALE_BYTES:
                raise ValueError('Dev Room 语言版本超过保存限制。')

            def require_versions(sidecar_expected=locale_raw):
                self._check_current_root(root)
                latest_source = self._checked_path(root, *DEV_ROOM_PARTS, identifier + '.md')
                if latest_source.exists():
                    with latest_source.open('rb') as source:
                        latest_raw = source.read(MAX_BODY_BYTES + MAX_HEADER_BYTES + 1)
                else:
                    latest_raw = None
                if latest_raw != source_raw or self._locale_raw(root, identifier)[0] != sidecar_expected or self._matched_catalog(current, self._catalog()) != entry:
                    raise DevRoomConflict('文档来源或语言版本已有更新，请保留草稿并重新读取。')

            require_versions()
            if locale_raw == new_locale:
                return self._state_localized(root, identifier, language, catalog)
            if locale_raw is not None:
                backup_parts = (*DEV_ROOM_PARTS, '.history', identifier, 'locales', hashlib.sha256(locale_raw).hexdigest() + '.json')
                self._mkdir(root, *backup_parts[:-1])
                backup = self._checked_path(root, *backup_parts)
                if backup.exists():
                    with backup.open('rb') as source:
                        if source.read(MAX_LOCALE_BYTES + 1) != locale_raw:
                            raise ValueError('Dev Room 语言历史版本校验失败，原文件已保留。')
                else:
                    self._atomic_write(root, backup_parts, locale_raw, before_replace=require_versions)
            self._mkdir(root, *DEV_ROOM_PARTS, '.locales')
            parts = (*DEV_ROOM_PARTS, '.locales', identifier + '.json')
            self._atomic_write(root, parts, new_locale, before_replace=require_versions)
            if creating:
                try:
                    self._atomic_write(root, (*DEV_ROOM_PARTS, identifier + '.md'), new_source,
                                       before_replace=lambda: require_versions(new_locale))
                except Exception:
                    # Only undo our own new sidecar; never touch a replacement or
                    # a source document another writer created in the meantime.
                    if self._locale_raw(root, identifier)[0] == new_locale:
                        self._checked_path(root, *parts).unlink()
                    raise
            return self._state_localized(root, identifier, language, catalog)
