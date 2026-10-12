"""Language-aware Dev Room content imports and Editor receipt-backed updates.

Reads do not create storage. Existing Markdown headers remain unchanged. Unity
assets are read through the bounded source adapter and written only by its Editor
bridge; this service writes durable, individually identified mailbox requests.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import uuid

from dev_room import DevRoomService, DEV_ROOM_PARTS, MAX_DOCUMENTS
import dev_room_media as media_store


NAMESPACE = uuid.UUID('cd51e6d1-a6ec-5bca-a9bd-70eaf0348ae5')
INDEX_PARTS = (*DEV_ROOM_PARTS, '.unity-sync.json')
OPERATION_PARTS = (*DEV_ROOM_PARTS, '.unity-sync', 'operations')
MAX_STATE_BYTES = 16 * 1024 * 1024
MAX_OPERATION_BYTES = 4 * 1024 * 1024
_SHA = re.compile(r'[0-9a-f]{64}')
_GUID = re.compile(r'[0-9a-f]{32}')


class DevRoomSyncConflict(ValueError):
    def __init__(self, message, code='sync_conflict', *, accepted=False):
        super().__init__(message)
        self.code = code
        self.accepted = accepted


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _request_id(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise ValueError('同步请求身份无效。') from exc
    return value


def _valid_document_file_id(value):
    return type(value) is int and value != 0 and -(2 ** 63) <= value <= 2 ** 63 - 1


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Dev Room 本地记录包含重复字段。')
        result[key] = value
    return result


def _local_template(body):
    """Check the local fixed-slot grammar without resolving any source/media."""
    marker = '<!-- rr-dev-room:'
    first, separator, remainder = body.partition('\n')
    first = first.rstrip('\r')
    if not separator or not first.startswith(marker + 'v1 ') or not first.endswith(' -->'):
        raise ValueError('请保留本地模板顶部的来源注释。')
    identity = json.loads(first[len(marker + 'v1 '):-4], object_pairs_hook=_unique_json)
    if (not isinstance(identity, dict) or set(identity) != {'id', 'guid'}
            or not isinstance(identity['id'], str) or not _GUID.fullmatch(str(identity['guid']))):
        raise ValueError('本地模板来源身份无效。')
    newline = r'\r?\n'
    prefix = re.match(r'\A# ([^\r\n]+)' + newline * 2 + re.escape(marker + 'summary -->') + newline
                      + r'(.*?)' + newline + re.escape(marker + 'summary-end -->') + newline * 2, remainder, re.S)
    if not prefix:
        raise ValueError('请保留本地模板的标题和摘要结构。')
    fields = [prefix.group(1), prefix.group(2)]; remainder = remainder[prefix.end():]
    count = 0; opaque_media = []
    while remainder and count < 128:
        match = re.match(re.escape(marker + f'section {count} -->') + newline + r'## ([^\r\n]+)' + newline
                         + r'(.*?)' + newline + re.escape(marker + f'section-end {count} -->') + newline * 2, remainder, re.S)
        if not match:
            raise ValueError('请保留本地模板既有章节的数量和顺序。')
        fields.extend((match.group(1), match.group(2)))
        # These comments are hidden local metadata while disconnected. Keep
        # their literal payload per slot; do not parse paths or image identities.
        opaque_media.append(tuple(line for line in match.group(2).splitlines()
                                  if '<!-- codex-dev-room-media' in line))
        count += 1; remainder = remainder[match.end():]
    if not count or remainder or any(marker in value for value in fields):
        raise ValueError('本地模板章节结构或保留注释无效。')
    return identity, count, prefix.group(1), tuple(opaque_media)


def content_revision(document):
    """v2 content revision includes captions, references and actual pixels."""
    import unity_dev_room_documents
    return unity_dev_room_documents.document_content_revision(document)


def text_revision(document):
    """Source text/caption version, independent of image pixels and bindings."""
    digest = hashlib.sha256()
    def add(value):
        raw = str(value or '').encode('utf-8')
        digest.update(struct.pack('>I', len(raw))); digest.update(raw)
    add(document['title']); add(document['summary'])
    digest.update(struct.pack('>I', len(document['sections'])))
    for section in document['sections']:
        add(section['title']); add(section['body']); add(section.get('imageCaption', ''))
    return digest.hexdigest()


class DevRoomSyncService:
    def __init__(self, document_library, workspace, *, dev_room=None, source_adapter=None, source_bindings=None,
                 source_sync_enabled=True):
        if type(source_sync_enabled) is not bool:
            raise ValueError('游戏来源连接开关须为布尔值。')
        self.source_sync_enabled = source_sync_enabled
        self.library = document_library
        self.dev_room = dev_room or DevRoomService(document_library)
        self.configured_workspace = Path(workspace)
        if not self.configured_workspace.is_absolute():
            raise ValueError('Unity 工作区须为完整路径。')
        # A deferred production connection must not even resolve/check the live
        # project path. Only explicitly enabled source fixtures/connections do so.
        self.workspace = self.configured_workspace.resolve() if source_sync_enabled else self.configured_workspace
        if source_adapter is None and source_sync_enabled:
            import unity_dev_room_documents
            source_adapter = unity_dev_room_documents
        self.sources = source_adapter
        self.source_bindings = deepcopy(source_bindings)

    def _source_connection(self):
        return {'state': 'connected' if self.source_sync_enabled else 'deferred', 'enabled': self.source_sync_enabled}

    def _require_source_sync(self):
        if not self.source_sync_enabled:
            raise DevRoomSyncConflict('游戏来源尚未连接；当前仅保存本地内容。', 'source_not_connected', accepted=False)

    def _check_workspace(self):
        self._require_source_sync()
        for component in (self.configured_workspace, *self.configured_workspace.parents):
            info = component.lstat()
            if component.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Unity 工作区路径不能含文件链接。')
        if not self.configured_workspace.is_dir() or self.configured_workspace.resolve() != self.workspace:
            raise DevRoomSyncConflict('Unity 工作区路径已经改变，原同步记录已保留。', 'source_changed')


    def _read_json(self, root, parts, *, missing=None, maximum=MAX_STATE_BYTES):
        path = self.dev_room._checked_path(root, *parts)
        if not path.exists():
            return missing, ''
        with path.open('rb') as source:
            raw = source.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError('Dev Room 同步记录超过读取限制。')
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=self.sources._unique_json if self.sources else _unique_json)
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Dev Room 同步记录有误，原记录已保留。') from exc
        if not isinstance(value, dict):
            raise ValueError('Dev Room 同步记录有误，原记录已保留。')
        return value, _sha(raw)

    def _index(self, root, inventory):
        empty = {'schemaVersion': 2, 'projectId': inventory['projectId'],
                 'workspace': str(self.workspace), 'libraryGuid': inventory['library']['guid'],
                 'bindings': {}, 'catalog': None}
        index, revision = self._read_json(root, INDEX_PARTS, missing=empty)
        if (index.get('schemaVersion') not in (1, 2) or not isinstance(index.get('bindings'), dict)
                or len(index['bindings']) > MAX_DOCUMENTS
                or index.get('projectId') != inventory['projectId']
                or index.get('libraryGuid') != inventory['library']['guid']
                or not isinstance(index.get('workspace'), str)
                or Path(index['workspace']).resolve() != self.workspace):
            raise DevRoomSyncConflict('Unity 项目或文档库来源已经改变，原绑定已保留。', 'source_changed')
        for identifier, binding in index['bindings'].items():
            self.dev_room._id(identifier)
            if (not isinstance(binding, dict) or binding.get('documentId') != identifier
                    or not _GUID.fullmatch(str(binding.get('unityGuid', '')))
                    or not _valid_document_file_id(binding.get('localFileId', 11400000))
                    or not isinstance(binding.get('unityDocumentId'), str)
                    or any(not isinstance(binding.get(key), str) for key in
                           ('assetPath', 'categoryTitle', 'sourceUpdatedAt', 'lastSyncedAt'))
                    or any(type(binding.get(key)) is not int for key in ('category', 'categoryOrder', 'order'))
                    or any(not _SHA.fullmatch(str(binding.get(key, ''))) for key in
                           ('lastConsoleRevision', 'lastUnityRevision', 'lastMetaRevision', 'lastContentSha256'))):
                raise ValueError('Dev Room 来源绑定无效，原记录已保留。')
            fields = [inventory['projectId'], inventory['library']['guid'], binding['unityGuid']]
            if binding.get('scope') == 'displayContent' or binding.get('localFileId', 11400000) != 11400000:
                fields.append(str(binding['localFileId']))
            expected_id = str(uuid.uuid5(NAMESPACE, '\n'.join(fields)))
            if identifier != expected_id:
                raise ValueError('Dev Room 文档与原来源命名空间不匹配，原记录已保留。')
        catalog = index.get('catalog')
        if catalog is not None:
            if (not isinstance(catalog, dict) or not _SHA.fullmatch(str(catalog.get('consoleRevision', '')))):
                raise ValueError('Dev Room 目录绑定无效，原记录已保留。')
            self.dev_room._id(catalog.get('documentId'))
        return index, revision

    @contextmanager
    def _index_lock(self, root):
        self.dev_room._mkdir(root, *DEV_ROOM_PARTS)
        path = self.dev_room._checked_path(root, *DEV_ROOM_PARTS, '.unity-sync.lock')
        with path.open('a+b') as lock:
            lock.seek(0, os.SEEK_END)
            if not lock.tell():
                lock.write(b'\0')
                lock.flush()
            lock.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise OSError('另一处正在同步 Dev Room，请稍后重试。') from exc
            try:
                self.dev_room._checked_path(root, *DEV_ROOM_PARTS, '.unity-sync.lock')
                yield
            finally:
                lock.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _write_json(self, root, parts, value, *, before_replace=None):
        raw = _json_bytes(value)
        if len(raw) > MAX_STATE_BYTES:
            raise ValueError('Dev Room 同步记录超过保存限制。')
        self.dev_room._mkdir(root, *parts[:-1])
        self.dev_room._atomic_write(root, parts, raw, before_replace=before_replace)
        return _sha(raw)








    def _operations(self, root):
        directory = self.dev_room._checked_path(root, *OPERATION_PARTS)
        if not directory.exists():
            return []
        result = []
        for path in directory.iterdir():
            if path.suffix != '.json':
                continue
            _request_id(path.stem)
            operation = self._read_json(root, (*OPERATION_PARTS, path.name), maximum=MAX_OPERATION_BYTES)[0]
            if operation.get('status') in {'prepared', 'pending', 'unknown'}:
                result.append({'requestId': path.stem, 'documentId': operation.get('documentId'),
                               'status': 'pending' if operation['status'] == 'pending' else 'unknown'})
        return result



    def _operation(self, root, request_id):
        return self._read_json(root, (*OPERATION_PARTS, request_id + '.json'), maximum=MAX_OPERATION_BYTES)[0]


    def _finish(self, root, operation, status, **values):
        operation.update(status=status, updatedAt=_now(), **values)
        self._write_json(root, (*OPERATION_PARTS, operation['requestId'] + '.json'), operation)
        return self._public(operation)







    # v2 methods below replace legacy text-only operations while preserving the
    # original IDs, index file, history and stable operation storage.
    def _inventory(self):
        self._require_source_sync()
        self._check_workspace()
        inventory = (self.sources.read_inventory(self.workspace) if self.source_bindings is None else
                     self.sources.read_explicit_inventory(self.workspace, self.source_bindings))
        if (not isinstance(inventory, dict) or Path(inventory.get('workspace', '')).resolve() != self.workspace
                or not _SHA.fullmatch(str(inventory.get('projectId', '')))
                or not isinstance(inventory.get('documents'), list) or len(inventory['documents']) > MAX_DOCUMENTS - 2):
            raise ValueError('Unity 文档来源无法核对。')
        seen = set()
        for document in inventory['documents']:
            key = (document.get('guid'), document.get('localFileId'))
            if (not _valid_document_file_id(key[1]) or key in seen or not _GUID.fullmatch(str(key[0]))
                    or not isinstance(document.get('expectedLibrary'), dict)
                    or any(not _SHA.fullmatch(str(document.get(k, ''))) for k in
                           ('revision', 'metaRevision', 'contentRevision', 'structureRevision', 'mediaRevision'))):
                raise ValueError('Unity 文档来源身份或版本无效。')
            seen.add(key)
            self.dev_room._title(document.get('title'))
            self.dev_room._body(self.sources.document_to_markdown(document))
        return inventory

    def _document_id(self, inventory, document):
        fields = [inventory['projectId'], inventory['library']['guid'], document['guid']]
        if document.get('scope') == 'displayContent' or document.get('localFileId', 11400000) != 11400000:
            fields.append(str(document['localFileId']))
        return str(uuid.uuid5(NAMESPACE, '\n'.join(fields)))

    def _source(self, inventory, binding):
        matches = [d for d in inventory['documents'] if d['guid'] == binding['unityGuid']
                   and d['localFileId'] == binding.get('localFileId', 11400000)
                   and d['id'] == binding['unityDocumentId'] and d['path'] == binding['assetPath']]
        if len(matches) != 1:
            raise DevRoomSyncConflict('原 Unity 文档来源已消失或改变，未写入。', 'source_missing')
        return matches[0]

    def _localized(self, root, identifier, language):
        return self.dev_room._localized(root, self.dev_room._read(root, identifier)[0], language, self.dev_room._catalog())

    def _local_versions(self, root, identifier, language):
        current = self.dev_room._read(root, identifier)[0]
        locale_raw = self.dev_room._locale_raw(root, identifier)[0]
        self.dev_room._locale(locale_raw, identifier)
        localized = self._localized(root, identifier, language)
        return {'sourceRevision': current['revision'] if current else '',
                'localeRawSha256': _sha(locale_raw) if locale_raw is not None else '',
                'revision': localized['revision'] if localized else ''}

    def _view_revision(self, localized, baseline):
        """Language revision plus fixed structure and selected image identities."""
        if localized.get('translationMissing'):
            content_hash, media_hash = '', baseline['mediaRevision']
        else:
            parsed = self.sources.markdown_to_document(localized['body'], baseline)
            content_hash = self.sources.document_content_revision(parsed)
            media_hash = self.sources.document_media_revision(parsed)
        return _sha(_json_bytes({'schema': 'dev-room-content-v2', 'textRevision': localized['revision'],
                    'contentRevision': content_hash, 'mediaRevision': media_hash,
                    'structureRevision': baseline['structureRevision']}))

    def _local_changed(self, root, identifier, binding, language):
        current = self._local_versions(root, identifier, language)
        return (current['sourceRevision'] != binding['lastConsoleRevision']
                or current['localeRawSha256'] != binding.get('lastLocaleRawSha256', ''))

    def _category(self, inventory, document):
        if document.get('scope') == 'displayContent':
            return {'id': document['category'], 'title': '设备私有展示', 'order': -1, 'summary': ''}
        return next(c for c in inventory['categories'] if c['id'] == document['category'])

    def _binding(self, root, inventory, document, language, request_id, *, console_revision=None):
        identifier, category = self._document_id(inventory, document), self._category(inventory, document)
        versions = self._local_versions(root, identifier, language)
        return {'documentId': identifier, 'unityDocumentId': document['id'], 'unityGuid': document['guid'],
                'localFileId': document['localFileId'], 'assetPath': document['path'],
                'scope': document.get('scope', 'globalLibrary'), 'category': document['category'],
                'categoryTitle': category['title'], 'categoryOrder': category['order'], 'order': document['order'],
                'sourceUpdatedAt': document.get('sourceUpdatedAt', ''), 'lastConsoleRevision': versions['sourceRevision'],
                'lastLocaleRawSha256': versions['localeRawSha256'],
                'lastLocalizedRevisions': {language: console_revision or versions['revision']},
                'lastUnityRevision': document['revision'], 'lastMetaRevision': document['metaRevision'],
                'lastLibraryRevision': document['expectedLibrary']['revision'],
                'lastContentSha256': document['contentRevision'], 'lastDocument': deepcopy(document),
                'lastSyncRequestId': request_id, 'lastSyncedAt': _now(), 'syncLanguage': language}

    def _source_changed(self, source, binding):
        old = binding.get('lastDocument')
        return (source['revision'] != binding['lastUnityRevision'] or source['metaRevision'] != binding['lastMetaRevision']
                or bool(old and (source['mediaRevision'] != old['mediaRevision']
                    or source['structureRevision'] != old['structureRevision']
                    or source['expectedLibrary'] != old['expectedLibrary'])))

    def _catalog_body(self, inventory, identifiers):
        lines = ['# Dev Room', '']
        groups = [('设备私有展示', [d for d in inventory['documents'] if d.get('scope') == 'displayContent'])]
        groups.extend((c['title'], [d for d in inventory['documents'] if d.get('scope') != 'displayContent' and d['category'] == c['id']])
                      for c in sorted(inventory['categories'], key=lambda c: c['order']))
        for title, documents in groups:
            if not documents:
                continue
            lines.extend(['## ' + title, ''])
            for document in documents:
                identifier = identifiers[(document['guid'], document['localFileId'])]
                lines.append('- [' + document['title'].replace('[', '\\[').replace(']', '\\]') + '](' + identifier + '.md)')
            lines.append('')
        return self.dev_room._body('\n'.join(lines))

    def _plan(self, root, inventory, index, index_revision, language):
        changes, bases = [], {}
        for identifier, binding in index['bindings'].items():
            try:
                self._source(inventory, binding)
            except DevRoomSyncConflict:
                changes.append({'action': 'conflict', 'documentId': identifier, 'reason': 'source_missing'})
        for source in inventory['documents']:
            identifier = self._document_id(inventory, source)
            current = self.dev_room._read(root, identifier)[0]
            bases[identifier] = self._local_versions(root, identifier, language)
            binding = index['bindings'].get(identifier)
            if not binding:
                action, reason = ('conflict', 'unbound_document_exists') if current else ('create', '')
            elif current is None:
                action, reason = 'conflict', 'console_document_missing'
            else:
                local_changed, source_changed = self._local_changed(root, identifier, binding, language), self._source_changed(source, binding)
                if local_changed and source_changed:
                    action, reason = 'conflict', 'both_changed'
                elif local_changed:
                    action, reason = 'preserve', 'console_language_or_source_changed'
                elif source_changed:
                    action, reason = 'update', ''
                elif 'lastDocument' not in binding:
                    action, reason = 'reconcile', 'v2_media_baseline'
                else:
                    action, reason = 'unchanged', ''
            category = self._category(inventory, source)
            changes.append({'action': action, 'documentId': identifier, 'unityDocumentId': source['id'],
                            'title': source['title'], 'category': source['category'], 'categoryTitle': category['title'],
                            'categoryOrder': category['order'], 'order': source['order'], 'scope': source.get('scope'), 'reason': reason})
        identifiers = {(d['guid'], d['localFileId']): self._document_id(inventory, d) for d in inventory['documents']}
        catalog, overview = index.get('catalog'), self.dev_room._read(root, 'overview')[0]
        catalog_id = catalog['documentId'] if catalog else ('overview' if not overview['body'].strip() else
            str(uuid.uuid5(NAMESPACE, inventory['projectId'] + '\n' + inventory['library']['guid'] + '\ncatalog')))
        catalog_doc, catalog_body = self.dev_room._read(root, catalog_id)[0], self._catalog_body(inventory, identifiers)
        bases[catalog_id] = self._local_versions(root, catalog_id, language)
        catalog_changed = catalog_doc and catalog_doc['revision'] != (catalog or {}).get('consoleRevision', '')
        catalog_action = ('preserve' if catalog and (catalog_changed or bases[catalog_id]['localeRawSha256']) else
                          'conflict' if not catalog and catalog_doc and catalog_id != 'overview' else
                          'index' if not catalog_doc or catalog_doc['body'] != catalog_body else 'unchanged')
        changes.append({'action': catalog_action, 'documentId': catalog_id, 'unityDocumentId': None,
                        'title': catalog_doc['title'] if catalog_doc else 'Dev Room 文档目录',
                        'reason': 'catalog_preserved' if catalog_action == 'preserve' else ''})
        snapshot = [{k: d[k] for k in ('id', 'guid', 'localFileId', 'path', 'revision', 'metaRevision',
                    'structureRevision', 'mediaRevision', 'expectedLibrary')} for d in inventory['documents']]
        frozen = {'root': str(root), 'workspace': str(self.workspace), 'projectId': inventory['projectId'], 'language': language,
                  'indexRevision': index_revision, 'sourceRevision': _sha(_json_bytes(snapshot)), 'bases': bases,
                  'changes': changes, 'catalogRevision': bases[catalog_id]['sourceRevision']}
        return {**frozen, 'planSha256': _sha(_json_bytes(frozen)),
                'canImport': not any(c['action'] == 'conflict' for c in changes)}, catalog_body

    def preview(self, expectedRoot, language='zh'):
        self._require_source_sync()
        language = self.dev_room._language(language)
        with self.dev_room._scope(expectedRoot) as root:
            inventory = self._inventory()
            index, revision = self._index(root, inventory)
            result, _ = self._plan(root, inventory, index, revision, language)
            self.dev_room._check_current_root(root)
            return result

    @staticmethod
    def _public(operation):
        return {k: v for k, v in operation.items() if k not in {'request', 'fingerprint', 'localVersions', 'localeExpiry'}}

    def _prior(self, root, payload, kind):
        old = self._operation(root, payload['requestId'])
        if old and (old.get('fingerprint') != _sha(_json_bytes(payload)) or old.get('kind') != kind):
            raise DevRoomSyncConflict('同一请求不能更换内容、语言或目标。', 'request_id_reused', accepted=True)
        return old

    def _reserve(self, root, payload, kind, **values):
        operation = {'schemaVersion': 2, 'requestId': payload['requestId'], 'kind': kind, 'accepted': True,
                     'fingerprint': _sha(_json_bytes(payload)), 'status': 'prepared', 'language': payload['language'],
                     'createdAt': _now(), **values}
        self._write_json(root, (*OPERATION_PARTS, payload['requestId'] + '.json'), operation)
        return operation, False

    def _payload(self, payload, keys, *, push=False):
        if not isinstance(payload, dict) or set(payload) != set(keys):
            raise ValueError('Dev Room 同步请求字段无效。')
        _request_id(payload['requestId'])
        self.dev_room._language(payload['language'])
        drafts = payload['draftIds']
        if not isinstance(drafts, list) or len(drafts) > MAX_DOCUMENTS:
            raise ValueError('Dev Room 草稿身份无效。')
        for identifier in drafts:
            self.dev_room._id(identifier)
        blocked = payload.get('documentId') in drafts if push else bool(drafts)
        if blocked:
            raise DevRoomSyncConflict('请先保存或保留未保存的 Dev Room 草稿，再同步。', 'unsaved_draft')

    def status(self, expectedRoot, language='zh'):
        language = self.dev_room._language(language)
        with self.dev_room._scope(expectedRoot) as root:
            if not self.source_sync_enabled:
                self.dev_room._check_current_root(root)
                return {'root': str(root), 'language': language, 'enabled': False,
                        'sourceConnection': self._source_connection(), 'sourceDocumentCount': 0,
                        'bindings': [], 'pending': []}
            inventory = self._inventory()
            index, revision = self._index(root, inventory)
            bindings = []
            for identifier, binding in index['bindings'].items():
                public = {k: binding.get(k, '') for k in ('documentId', 'unityDocumentId', 'unityGuid', 'localFileId',
                    'assetPath', 'category', 'categoryTitle', 'categoryOrder', 'order', 'sourceUpdatedAt', 'lastSyncedAt', 'scope')}
                localized = self._localized(root, identifier, language)
                catalog = index.get('catalog') or {}
                managed_navigation = (localized and catalog.get('documentId') == identifier
                                      and catalog.get('consoleRevision') == localized.get('sourceRevision')
                                      and self.dev_room._locale_raw(root, identifier)[0] is None)
                public.update(translationStale=bool(localized and localized.get('translationStale') and not managed_navigation),
                              translationMissing=bool(localized and localized.get('translationMissing') and not managed_navigation))
                try:
                    source = self._source(inventory, binding)
                    local_changed, source_changed = self._local_changed(root, identifier, binding, language), self._source_changed(source, binding)
                    state = 'conflict' if local_changed and source_changed else 'console_changed' if local_changed else 'unity_changed' if source_changed else 'synced'
                    if source.get('writebackSupported') is False:
                        state = 'unsupported_image_identity'
                    if public['translationStale']:
                        state = 'translation_stale'
                    elif public['translationMissing']:
                        state = 'translation_missing'
                    public.update(lastUnityRevision=source['revision'], expectedUnityRevision=source['revision'],
                                  lastConsoleRevision=self._view_revision(localized, binding.get('lastDocument', source)))
                except DevRoomSyncConflict:
                    state = 'source_missing'
                bindings.append({**public, 'status': state, 'lastSync': state, 'language': language})
            self.dev_room._check_current_root(root)
            return {'root': str(root), 'workspace': str(self.workspace), 'projectId': inventory['projectId'],
                    'enabled': True, 'sourceConnection': self._source_connection(),
                    'language': language, 'library': inventory['library'], 'indexRevision': revision,
                    'sourceDocumentCount': len(inventory['documents']), 'bindings': sorted(bindings,
                    key=lambda b: (b['categoryOrder'], b['order'], b['unityDocumentId'])), 'pending': self._operations(root)}

    def _save_import(self, root, identifier, source, expected, language, binding=None):
        if self._local_versions(root, identifier, language) != expected:
            raise DevRoomSyncConflict('语言或原文在导入期间改变，已保留。', 'console_changed', accepted=True)
        current, old_locale_raw = self.dev_room._read(root, identifier)[0], self.dev_room._locale_raw(root, identifier)[0]
        old_locale = self.dev_room._locale(old_locale_raw, identifier)
        if old_locale and (not current or old_locale['sourceRevision'] != current['revision']):
            raise DevRoomSyncConflict('语言来源已经失配，原 sidecar 已保留。', 'locale_source_changed', accepted=True)
        entry = self.dev_room._matched_catalog(current, self.dev_room._catalog())
        variants = deepcopy(old_locale['variants'] if old_locale else entry['variants'] if entry else {})
        stale = set(old_locale.get('staleLanguages', [])) if old_locale else set()
        original_languages = set(variants) | (set(entry['variants']) if entry else set()) | stale
        baseline = binding.get('lastDocument') if binding else None
        if baseline is None and binding and binding.get('lastContent'):
            baseline = deepcopy(binding['lastContent'])
            for section, metadata in zip(baseline['sections'], binding.get('sectionMetadata', [])):
                section['imageCaption'] = metadata.get('imageCaption', '')
        text_unchanged = baseline is not None and text_revision(baseline) == text_revision(source)
        if not text_unchanged:
            # Old translations are retained in history, not rebound to a source
            # they have never translated. Only this explicit import is current.
            variants = {}
            stale |= original_languages - {language}
        stale.discard(language)
        body = self.sources.document_to_markdown(source)
        old_source, old_source_raw = self.dev_room._read(root, identifier)
        header = json.dumps({'version': 1, 'id': identifier, 'title': source['title']}, ensure_ascii=False,
                            separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e')
        new_source_raw = ('<!-- codex-dev-room ' + header + ' -->\n' + body).encode('utf-8')
        if old_source_raw == new_source_raw and text_unchanged:
            return old_source
        new_entry = self.dev_room._matched_catalog({'id': identifier, 'title': source['title'], 'body': body,
                        'revision': _sha(new_source_raw)}, self.dev_room._catalog())
        if new_entry and (current is None or text_unchanged):
            for variant_language, variant in new_entry['variants'].items():
                variants.setdefault(variant_language, deepcopy(variant))
            if language in new_entry['variants']:
                variants[language] = deepcopy(new_entry['variants'][language])
            else:
                variants[language] = {'title': source['title'], 'body': body}
        else:
            variants[language] = {'title': source['title'], 'body': body}
        updated = {'version': 1, 'id': identifier, 'sourceRevision': _sha(new_source_raw),
                   'sourceLanguage': language, 'variants': variants}
        if stale:
            updated['staleLanguages'] = sorted(stale)
        if len(_json_bytes(updated)) > 2 * 512 * 1024 + 8192:
            raise ValueError('导入后语言版本超过保存限制。')
        new_locale_raw = _json_bytes(updated)
        with self.dev_room._write_lock(root):
            def require(locale_expected=old_locale_raw):
                self.dev_room._check_current_root(root)
                if (self.dev_room._read(root, identifier)[1] != old_source_raw
                        or self.dev_room._locale_raw(root, identifier)[0] != locale_expected):
                    raise DevRoomSyncConflict('导入期间另一处修改了语言或原文，已保留。', 'console_changed', accepted=True)
            require()
            if entry and not text_unchanged:
                catalog_backup = (*DEV_ROOM_PARTS, '.history', identifier, 'locales', 'catalog-' + current['revision'] + '.json')
                self.dev_room._mkdir(root, *catalog_backup[:-1])
                catalog_bytes = _json_bytes(entry)
                existing = self.dev_room._checked_path(root, *catalog_backup)
                if existing.exists():
                    if existing.read_bytes() != catalog_bytes:
                        raise ValueError('内置语言历史校验失败。')
                else:
                    self.dev_room._atomic_write(root, catalog_backup, catalog_bytes, before_replace=require)
            if old_source_raw is not None:
                backup = (*DEV_ROOM_PARTS, '.history', identifier, old_source['revision'] + '.md')
                self.dev_room._mkdir(root, *backup[:-1])
                old_backup = self.dev_room._checked_path(root, *backup)
                if old_backup.exists():
                    if old_backup.read_bytes() != old_source_raw:
                        raise ValueError('原文历史版本校验失败。')
                else:
                    self.dev_room._atomic_write(root, backup, old_source_raw, before_replace=require)
            if old_locale_raw is not None:
                backup = (*DEV_ROOM_PARTS, '.history', identifier, 'locales', _sha(old_locale_raw) + '.json')
                self.dev_room._mkdir(root, *backup[:-1])
                old_backup = self.dev_room._checked_path(root, *backup)
                if old_backup.exists():
                    if old_backup.read_bytes() != old_locale_raw:
                        raise ValueError('语言历史版本校验失败。')
                else:
                    self.dev_room._atomic_write(root, backup, old_locale_raw, before_replace=require)
            self.dev_room._mkdir(root, *DEV_ROOM_PARTS, '.locales')
            locale_parts = (*DEV_ROOM_PARTS, '.locales', identifier + '.json')
            self.dev_room._atomic_write(root, locale_parts, new_locale_raw, before_replace=require)
            try:
                self.dev_room._atomic_write(root, (*DEV_ROOM_PARTS, identifier + '.md'), new_source_raw,
                                           before_replace=lambda: require(new_locale_raw))
            except Exception:
                # Undo only this import's sidecar if the source stayed untouched.
                if (self.dev_room._read(root, identifier)[1] == old_source_raw
                        and self.dev_room._locale_raw(root, identifier)[0] == new_locale_raw):
                    if old_locale_raw is None:
                        self.dev_room._checked_path(root, *locale_parts).unlink()
                    else:
                        self.dev_room._atomic_write(root, locale_parts, old_locale_raw,
                                                   before_replace=lambda: require(new_locale_raw))
                raise
        return self.dev_room._read(root, identifier)[0]

    def import_documents(self, payload):
        self._require_source_sync()
        self._payload(payload, ('requestId', 'expectedRoot', 'planSha256', 'expectedIndexRevision', 'draftIds', 'language'))
        if not _SHA.fullmatch(str(payload['planSha256'])):
            raise ValueError('导入预览版本无效。')
        with self.dev_room._scope(payload['expectedRoot']) as root, self._index_lock(root):
            old = self._prior(root, payload, 'import')
            if old:
                return self._public(old)
            inventory = self._inventory()
            index, revision = self._index(root, inventory)
            plan, catalog_body = self._plan(root, inventory, index, revision, payload['language'])
            if revision != payload['expectedIndexRevision'] or plan['planSha256'] != payload['planSha256']:
                raise DevRoomSyncConflict('预览之后文档、语言或来源已变化，请重新预览。', 'preview_changed')
            if not plan['canImport']:
                raise DevRoomSyncConflict('来源或两边修订有冲突，原文与语言稿已保留。')
            operation, _ = self._reserve(root, payload, 'import', changes=plan['changes'], completed=[])
            index['schemaVersion'] = 2
            sources = {self._document_id(inventory, d): d for d in inventory['documents']}
            try:
                for change in plan['changes']:
                    if change['action'] in {'unchanged', 'preserve'}:
                        continue
                    identifier = change['documentId']
                    self.dev_room._check_current_root(root)
                    latest = self._inventory()
                    if _sha(_json_bytes(latest['documents'])) != _sha(_json_bytes(inventory['documents'])):
                        raise DevRoomSyncConflict('游戏来源在导入期间改变，未继续导入。', 'source_changed', accepted=True)
                    if identifier in sources:
                        source = sources[identifier]
                        self._save_import(root, identifier, source, plan['bases'][identifier], payload['language'], index['bindings'].get(identifier))
                        index['bindings'][identifier] = self._binding(root, inventory, source, payload['language'], payload['requestId'])
                    else:
                        versions = self._local_versions(root, identifier, payload['language'])
                        if versions != plan['bases'][identifier]:
                            raise DevRoomSyncConflict('目录已修改，未覆盖。', 'console_changed', accepted=True)
                        saved = self.dev_room.save({'expectedRoot': str(root), 'id': identifier, 'title': change['title'],
                            'body': catalog_body, 'expectedRevision': versions['sourceRevision']})['document']
                        index['catalog'] = {'documentId': identifier, 'consoleRevision': saved['revision']}
                    self._write_json(root, INDEX_PARTS, index)
                    operation['completed'].append(identifier)
                    self._finish(root, operation, 'prepared')
                return self._finish(root, operation, 'applied' if operation['completed'] else 'unchanged', indexRevision=self._index(root, inventory)[1])
            except Exception as exc:
                self._finish(root, operation, 'failed', error=str(exc), code=getattr(exc, 'code', 'import_failed'))
                exc.accepted = True; exc.syncRequestId = payload['requestId']
                raise

    def _bound_context(self, root, identifier):
        index, _ = self._read_json(root, INDEX_PARTS)
        if not index or identifier not in index.get('bindings', {}):
            return None, None, None
        inventory = self._inventory()
        index, _ = self._index(root, inventory)
        binding = index['bindings'][identifier]
        return inventory, binding, self._source(inventory, binding)

    def document_state(self, expectedRoot, id='overview', language='zh'):
        result = self.dev_room.state(expectedRoot, id, language)
        result['sourceConnection'] = self._source_connection()
        if not self.source_sync_enabled:
            return result
        document = result.get('document')
        with self.dev_room._scope(expectedRoot) as root:
            try:
                index, _ = self._read_json(root, INDEX_PARTS)
                catalog = (index or {}).get('catalog') or {}
                navigation_id = catalog.get('documentId')
                navigation = self.dev_room._read(root, self.dev_room._id(navigation_id))[0] if navigation_id else None
                managed_navigation = (navigation and catalog.get('consoleRevision') == navigation['revision']
                                      and self.dev_room._locale_raw(root, navigation_id)[0] is None)
                navigation_title = '总案' if language == 'zh' else 'Overview'
                if managed_navigation:
                    for summary in result.get('documents', []):
                        if summary['id'] == navigation_id:
                            summary.update(title=navigation_title, translationMissing=False, generatedNavigation=True)
                if document is None:
                    return result
                if managed_navigation and document.get('translationMissing') and navigation_id == id:
                    # A verified generated index is navigation, not an untranslated
                    # authored document. Localize its label without writing a locale
                    # or guessing a source language for ordinary documents.
                    document.update(title=navigation_title,
                                    body=document.get('sourceBody', ''), translationMissing=False,
                                    generatedNavigation=True)
                _, binding, source = self._bound_context(root, id)
                if not source:
                    return result
                baseline = binding.get('lastDocument', source)
                document['textRevision'] = document['revision']
                document['revision'] = self._view_revision(document, baseline)
                parsed = self.sources.markdown_to_document(document['body'], baseline) if not document.get('translationMissing') else {'sections': []}
                slots = []
                for section in parsed['sections']:
                    value = json.loads(self.sources.media_to_json(section))
                    slots.append({'section': section['index'], 'index': section['index'], 'caption': section['imageCaption'],
                                  'image': value, 'hasImage': bool(section['image']['sha256']), 'editable': True})
                document.update(mediaSlots=slots, mediaSections=slots, syncSource={
                    'scope': source.get('scope', 'globalLibrary'), 'path': source['path'], 'guid': source['guid'],
                    'localFileId': source['localFileId'], 'id': source['id'], 'workspace': str(self.workspace),
                    'fixedSectionCount': len(source['sections']), 'sourceRevision': source['revision'],
                    'writebackSupported': source.get('writebackSupported', True)})
            except (ValueError, OSError) as exc:
                if document is not None:
                    document.update(mediaSlots=[], mediaSections=[], syncSourceUnavailable=str(exc))
            self.dev_room._check_current_root(root)
            return result

    def validate_save(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('保存请求无效。')
        identifier = self.dev_room._id(payload.get('id'))
        with self.dev_room._scope(payload.get('expectedRoot')) as root:
            index, _ = self._read_json(root, INDEX_PARTS)
            binding = index.get('bindings', {}).get(identifier) if index else None
            if not binding:
                return
            if not self.source_sync_enabled:
                canonical = self.dev_room._read(root, identifier)[0]
                if not canonical:
                    raise ValueError('本地模板来源已不存在，原绑定已保留。')
                before, count, _, canonical_media = _local_template(canonical['body'])
                after, changed_count, title, changed_media = _local_template(self.dev_room._body(payload.get('body')))
                if before != after or count != changed_count or title != payload.get('title'):
                    raise ValueError('请保留本地模板的来源身份、章节数量和顺序。')
                original_media = canonical_media
                if 'language' in payload:
                    language = self.dev_room._language(payload['language'])
                    current = self._localized(root, identifier, language)
                    local_body = current['body'] or current['sourceBody']
                    original_media = _local_template(local_body)[3]
                if original_media != changed_media:
                    raise ValueError('游戏来源尚未连接，请保留每个章节已有的图片元数据。')
                return
            language = self.dev_room._language(payload.get('language'))
            current = self._localized(root, identifier, language)
            baseline = binding.get('lastDocument')
            if baseline is None:
                _, _, baseline = self._bound_context(root, identifier)
            if not current or self._view_revision(current, baseline) != payload.get('expectedRevision'):
                raise DevRoomSyncConflict('保存语言版本或图片来源已改变，请保留草稿后重新读取。', 'console_changed')
            parsed = self.sources.markdown_to_document(payload.get('body'), baseline)
            if parsed['title'] != payload.get('title'):
                raise DevRoomSyncConflict('正文标题与文档名称不一致。', 'title_mismatch')
            for section in parsed['sections']:
                if section['image'].get('stagingName'):
                    media_store.read_object(self.dev_room, root, section['image']['stagingName'])
            # The HTTP route then calls the existing locale-aware save, which
            # compares the underlying source+sidecar version atomically.
            payload['expectedRevision'] = current['revision']

    def save_document(self, payload):
        """Keep media baseline pinned until the existing locale save completes."""
        if not isinstance(payload, dict):
            raise ValueError('Dev Room 保存请求无效。')
        identifier = self.dev_room._id(payload.get('id'))
        with self.dev_room._scope(payload.get('expectedRoot')) as root:
            index, _ = self._read_json(root, INDEX_PARTS)
            bound = index and identifier in index.get('bindings', {})
            if bound:
                with self._index_lock(root):
                    self.validate_save(payload)
                    self.dev_room.save(payload)
            else:
                self.dev_room.save(payload)
        return self.document_state(payload['expectedRoot'], identifier, payload.get('language'))

    def upload_media(self, payload):
        self._require_source_sync()
        if not isinstance(payload, dict) or set(payload) != {'expectedRoot', 'id', 'language', 'expectedRevision',
                                                           'section', 'filename', 'mimeType', 'base64'}:
            raise ValueError('图片上传请求字段无效。')
        identifier, language = self.dev_room._id(payload['id']), self.dev_room._language(payload['language'])
        raw, metadata = media_store.decode_upload(payload)
        with self.dev_room._scope(payload['expectedRoot']) as root, self._index_lock(root):
            _, binding, source = self._bound_context(root, identifier)
            if not binding:
                raise DevRoomSyncConflict('只有游戏既有章节的图片槽可上传。', 'unbound_document')
            current = self._localized(root, identifier, language)
            baseline = binding.get('lastDocument', source)
            view_revision = self._view_revision(current, baseline) if current else ''
            if not current or view_revision != payload['expectedRevision']:
                raise DevRoomSyncConflict('上传对应的语言文档已改变，请保留草稿。', 'console_changed')
            parsed = self.sources.markdown_to_document(current['body'], baseline)
            position = payload['section']
            if type(position) is not int or not 0 <= position < len(parsed['sections']):
                raise ValueError('图片章节不是游戏现有固定槽。')
            section = parsed['sections'][position]
            stored = media_store.store_object(self.dev_room, root, raw)
            if self._localized(root, identifier, language)['revision'] != current['revision']:
                raise DevRoomSyncConflict('图片已持久保存，但文档已改变，请重新核对。', 'console_changed')
            # Persist the upload's exact document/locale/slot provenance. A draft
            # token alone must not grant access to another document's objects.
            self._write_json(root, (*DEV_ROOM_PARTS, '.media', 'uploads', identifier, language,
                                   str(position), stored['stagingName'] + '.json'), {
                'schemaVersion': 1, 'documentId': identifier, 'language': language, 'section': position,
                'stagingName': stored['stagingName'], 'sha256': stored['sha256'],
                'unityGuid': source['guid'], 'localFileId': source['localFileId'],
                'structureRevision': baseline['structureRevision'], 'uploadedAt': _now(),
                'savedRevisionAtUpload': view_revision})
            image = {'section': position, 'imageCaption': section['imageCaption'], 'guid': '', 'fileID': 0, 'type': 3,
                     'resourcePath': 'UI/DevsRealm/ConsoleMedia/' + stored['sha256'],
                     'assetPath': 'Assets/Resources/UI/DevsRealm/ConsoleMedia/' + stored['stagingName'],
                     'sha256': stored['sha256'], 'stagingName': stored['stagingName']}
            return {**stored, 'section': position, 'image': image, 'expectedRevision': view_revision,
                    'language': language, 'savedToDocument': False}

    def draft_media(self, expectedRoot, id, section, revision, stagingName, language='zh'):
        """Read a registered unsaved image after reload, without committing it."""
        self._require_source_sync()
        identifier, language = self.dev_room._id(id), self.dev_room._language(language)
        name = media_store.object_name(stagingName)
        if not _SHA.fullmatch(str(revision)):
            raise ValueError('图片草稿所属文档版本无效。')
        try:
            position = int(section)
        except (ValueError, TypeError) as exc:
            raise ValueError('图片草稿章节无效。') from exc
        if str(position) != str(section):
            raise ValueError('图片草稿章节无效。')
        with self.dev_room._scope(expectedRoot) as root:
            _, binding, source = self._bound_context(root, identifier)
            if not binding:
                raise ValueError('图片草稿没有固定游戏来源绑定。')
            baseline = binding.get('lastDocument', source)
            current = self._localized(root, identifier, language)
            if not current or self._view_revision(current, baseline) != revision:
                raise DevRoomSyncConflict('图片草稿所属语言文档已改变，请重新读取。', 'console_changed')
            if not 0 <= position < len(baseline['sections']):
                raise ValueError('图片草稿章节不是既有固定槽。')
            parts = (*DEV_ROOM_PARTS, '.media', 'uploads', identifier, language, str(position), name + '.json')
            registration, _ = self._read_json(root, parts, maximum=4096)
            expected = {'schemaVersion': 1, 'documentId': identifier, 'language': language, 'section': position,
                        'stagingName': name, 'sha256': name.split('.')[0], 'unityGuid': source['guid'],
                        'localFileId': source['localFileId'], 'structureRevision': baseline['structureRevision']}
            if not registration or any(registration.get(key) != value for key, value in expected.items()):
                raise ValueError('图片草稿没有匹配此文档、语言和章节的上传记录。')
            path, metadata, _ = media_store.read_object(self.dev_room, root, name)
            if self._view_revision(self._localized(root, identifier, language), baseline) != revision:
                raise DevRoomSyncConflict('读取图片草稿期间语言文档改变。', 'console_changed')
            self.dev_room._check_current_root(root)
            return {'path': str(path), 'mimeType': metadata['mimeType'], 'mime': metadata['mimeType'],
                    'size': metadata['size'], 'sha256': metadata['sha256']}

    def media(self, expectedRoot, id, section, revision, language='zh'):
        self._require_source_sync()
        identifier, language = self.dev_room._id(id), self.dev_room._language(language)
        if not _SHA.fullmatch(str(revision)):
            raise ValueError('图片文档版本无效。')
        try:
            position = int(section)
        except (ValueError, TypeError) as exc:
            raise ValueError('图片章节无效。') from exc
        if str(position) != str(section):
            raise ValueError('图片章节无效。')
        with self.dev_room._scope(expectedRoot) as root:
            _, binding, source = self._bound_context(root, identifier)
            if not binding:
                raise ValueError('图片没有固定游戏来源绑定。')
            current = self._localized(root, identifier, language)
            baseline = binding.get('lastDocument', source)
            if not current or self._view_revision(current, baseline) != revision:
                raise DevRoomSyncConflict('图片所属语言文档已改变，请重新读取。', 'console_changed')
            parsed = self.sources.markdown_to_document(current['body'], baseline)
            if not 0 <= position < len(parsed['sections']):
                raise ValueError('图片章节无效。')
            image = parsed['sections'][position]['image']
            if not image['sha256']:
                raise FileNotFoundError('此章节没有图片。')
            if image.get('stagingName'):
                path, metadata, _ = media_store.read_object(self.dev_room, root, image['stagingName'])
            else:
                path = self.sources._path(self.workspace, image['assetPath'])
                raw, actual_sha = self.sources._read(self.workspace, image['assetPath'], media_store.MAX_MEDIA_BYTES)
                metadata = media_store.inspect_image(raw)
                actual_guid, actual_meta = self.sources._meta(self.workspace, image['assetPath'] + '.meta')
                if (actual_sha != image['sha256'] or (image.get('guid') and actual_guid != image['guid'])
                        or actual_meta != image.get('metaRevision', '')):
                    raise DevRoomSyncConflict('游戏图片来源已经改变，不能用旧版本展示。', 'media_changed')
            if self._view_revision(self._localized(root, identifier, language), baseline) != revision:
                raise DevRoomSyncConflict('读取图片期间语言文档改变。', 'console_changed')
            self.dev_room._check_current_root(root)
            return {'path': str(path), 'mimeType': metadata['mimeType'], 'mime': metadata['mimeType'],
                    'size': metadata['size'], 'sha256': metadata['sha256']}

    def _bridge_path(self, *parts, create=False):
        self._require_source_sync()
        self._check_workspace()
        path = self.workspace
        components = ('.codex', 'console-content-sync', 'v2', *parts)
        for index, part in enumerate(components):
            if not isinstance(part, str) or not part or part in {'.', '..'} or '/' in part or '\\' in part:
                raise ValueError('Unity 同步邮箱路径无效。')
            path = path / part
            if path.exists() or path.is_symlink():
                if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Unity 同步邮箱路径含链接。')
            elif create and index != len(components) - 1:
                path.mkdir(exist_ok=True)
        if not path.resolve().is_relative_to(self.workspace):
            raise ValueError('Unity 同步邮箱路径不能离开工作区。')
        return path

    def _session(self):
        path = self._bridge_path('session.json')
        if not path.is_file():
            raise DevRoomSyncConflict('游戏 Editor 内容桥尚未开启，请先启用本轮同步窗口。', 'bridge_unavailable')
        with path.open('rb') as session_file:
            raw = session_file.read(4097)
        if len(raw) > 4096:
            raise ValueError('Editor 同步窗口记录过大。')
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=self.sources._unique_json)
            expires = datetime.fromisoformat(value['expiresAt'].replace('Z', '+00:00'))
        except (ValueError, KeyError, UnicodeError) as exc:
            raise ValueError('Editor 同步窗口记录无效。') from exc
        if (value.get('schemaVersion') != 2 or value.get('enabled') is not True
                or not _GUID.fullmatch(str(value.get('editorInstanceNonce', '')))
                or Path(value.get('projectRoot', '')).resolve() != self.workspace
                or expires.tzinfo is None or expires <= datetime.now(timezone.utc)):
            raise DevRoomSyncConflict('Editor 同步窗口已关闭、过期或属于另一工作区。', 'bridge_unavailable')
        return value

    def _send_request(self, request):
        path = self._bridge_path('requests', request['requestId'] + '.json', create=True)
        raw = _json_bytes(request)
        if len(raw) > MAX_OPERATION_BYTES:
            raise ValueError('Unity 同步请求超过限制。')
        if path.exists():
            raise DevRoomSyncConflict('同一邮箱请求已经存在，只能核对回执，不能再送。', 'request_already_sent', accepted=True)
        temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as destination:
                destination.write(raw); destination.flush(); os.fsync(destination.fileno())
            self._bridge_path('requests', request['requestId'] + '.json')
            if path.exists():
                raise DevRoomSyncConflict('邮箱请求提交时已变化，只能核对。', 'request_already_sent', accepted=True)
            os.replace(temporary, path)
        finally:
            self._bridge_path('requests', request['requestId'] + '.json')
            temporary.unlink(missing_ok=True)

    def _stage_images(self, root, target):
        for section in target['sections']:
            image = section['image']
            if not image.get('stagingName'):
                continue
            _, metadata, raw = media_store.read_object(self.dev_room, root, image['stagingName'])
            if metadata['sha256'] != image['sha256']:
                raise ValueError('图片对象与确认内容不一致。')
            path = self._bridge_path('media', image['stagingName'], create=True)
            if path.exists():
                with path.open('rb') as existing:
                    previous = existing.read(media_store.MAX_MEDIA_BYTES + 1)
                if _sha(previous) != image['sha256']:
                    raise DevRoomSyncConflict('Editor 图片暂存对象校验失败。', 'media_changed', accepted=True)
            else:
                with path.open('xb') as destination:
                    destination.write(raw); destination.flush(); os.fsync(destination.fileno())
            self._bridge_path('media', image['stagingName'])

    def push_intent(self, payload):
        self._require_source_sync()
        self._payload(payload, ('requestId', 'expectedRoot', 'documentId', 'expectedRevision',
                               'expectedUnityRevision', 'draftIds', 'language'), push=True)
        identifier, language = self.dev_room._id(payload['documentId']), payload['language']
        if any(not _SHA.fullmatch(str(payload[k])) for k in ('expectedRevision', 'expectedUnityRevision')):
            raise ValueError('同步文档修订无效。')
        with self.dev_room._scope(payload['expectedRoot']) as root, self._index_lock(root):
            old = self._prior(root, payload, 'push')
            if old:
                return self._public(old)
            inventory = self._inventory()
            index, _ = self._index(root, inventory)
            binding = index['bindings'].get(identifier)
            if not binding:
                raise DevRoomSyncConflict('这份文档没有游戏来源绑定。', 'unbound_document')
            current = self._localized(root, identifier, language)
            source = self._source(inventory, binding)
            if source.get('writebackSupported') is False:
                raise DevRoomSyncConflict('Resources 图片缺少可核对的 Texture2D 身份；可以浏览，尚不能回写游戏。', 'unsupported_image_identity')
            baseline = binding.get('lastDocument', source)
            view_revision = self._view_revision(current, baseline) if current else ''
            if not current or view_revision != payload['expectedRevision'] or current['translationMissing']:
                raise DevRoomSyncConflict('当前选择的语言文档或图片已改变，请先保存。', 'console_changed')
            if source['revision'] != payload['expectedUnityRevision'] or self._source_changed(source, binding):
                raise DevRoomSyncConflict('游戏文档、结构或图片已有更新，未覆盖。', 'unity_changed')
            if any(o['documentId'] == identifier for o in self._operations(root)):
                raise DevRoomSyncConflict('此文档已有同步待核对，请读取原请求回执。', 'sync_pending', accepted=True)
            parsed = self.sources.markdown_to_document(current['body'], baseline)
            if parsed['title'] != current['title']:
                raise DevRoomSyncConflict('正文标题与文档名称不一致。', 'title_mismatch')
            target = {'title': parsed['title'], 'summary': parsed['summary'], 'sections': [
                {k: deepcopy(s[k]) for k in ('index', 'title', 'body', 'imageCaption', 'image')} for s in parsed['sections']]}
            checksum = self.sources.document_content_revision(parsed)
            if checksum == source['contentRevision'] and self.sources.document_media_revision(parsed) == source['mediaRevision']:
                operation, _ = self._reserve(root, payload, 'push', documentId=identifier)
                index['schemaVersion'] = 2
                index['bindings'][identifier] = self._binding(root, inventory, source, language, payload['requestId'])
                self._write_json(root, INDEX_PARTS, index)
                return self._finish(root, operation, 'unchanged')
            session = self._session()
            request = {'schemaVersion': 2, 'requestId': payload['requestId'], 'editorInstanceNonce': session['editorInstanceNonce'],
                'projectId': inventory['projectId'], 'projectLibraryGuid': inventory['library']['guid'],
                'workspace': str(self.workspace), 'language': language,
                'documentId': identifier, 'consoleRevision': view_revision, 'contentSha256': checksum,
                'expectedLibrary': deepcopy(source['expectedLibrary']), 'document': {k: source[k] for k in
                    ('path', 'id', 'guid', 'localFileId', 'revision', 'metaRevision', 'contentRevision', 'structureRevision', 'mediaRevision')},
                'target': target}
            operation, _ = self._reserve(root, payload, 'push', documentId=identifier, request=request,
                                      localVersions=self._local_versions(root, identifier, language))
            try:
                self._stage_images(root, target)
                if self._session()['editorInstanceNonce'] != session['editorInstanceNonce']:
                    raise DevRoomSyncConflict('Editor 同步窗口已改变，原请求待核对。', 'bridge_changed', accepted=True)
                if self._local_versions(root, identifier, language) != operation['localVersions']:
                    raise DevRoomSyncConflict('提交期间语言文档已有修改，原请求待核对。', 'console_changed', accepted=True)
                self._send_request(request)
                return self._finish(root, operation, 'pending')
            except Exception as exc:
                self._finish(root, operation, 'unknown', error=str(exc), code=getattr(exc, 'code', 'mailbox_unavailable'))
                exc.accepted = True; exc.syncRequestId = payload['requestId']
                raise

    def _reconcile_applied_languages(self, root, operation, request, source, require_index):
        """Journal local language expiry only after actual Editor/file proof.

        Caller holds index and document write locks. No canonical source is
        rewritten, and recovery repeats only metadata checks, never a game push.
        """
        identifier, language = operation['documentId'], operation['language']
        before = self._local_versions(root, identifier, language)
        journal = operation.get('localeExpiry')
        if (journal and journal.get('appliedUnityRevision') == source['revision']
                and journal.get('afterLocaleRawSha256') == before['localeRawSha256']
                and journal.get('before', {}).get('sourceRevision') == before['sourceRevision']):
            return journal['before'], before, journal.get('staleLanguages', [])
        changed = (source['contentRevision'] != request['document']['contentRevision']
                   or source['mediaRevision'] != request['document']['mediaRevision'])
        if not changed:
            return before, before, []
        current = self.dev_room._read(root, identifier)[0]
        old_raw = self.dev_room._locale_raw(root, identifier)[0]
        locale = self.dev_room._locale(old_raw, identifier)
        if not current or (locale and locale['sourceRevision'] != current['revision']):
            raise DevRoomSyncConflict('游戏已完成本轮写入，但本地语言来源已有改变；保留稿件待核对。', 'locale_source_changed', accepted=True)
        entry = self.dev_room._matched_catalog(current, self.dev_room._catalog())
        updated = deepcopy(locale) if locale else {'version': 1, 'id': identifier,
                   'sourceRevision': current['revision'], 'variants': deepcopy(entry['variants']) if entry else {}}
        selected = self._localized(root, identifier, language)
        if language not in updated['variants'] and selected and not selected['translationMissing']:
            updated['variants'][language] = {'title': selected['title'], 'body': selected['body']}
        stale = (set(updated.get('staleLanguages', [])) | {'zh', 'en'}) - {language}
        updated['staleLanguages'] = sorted(stale)
        new_raw = _json_bytes(updated)
        from dev_room import MAX_LOCALE_BYTES
        if len(new_raw) > MAX_LOCALE_BYTES:
            raise ValueError('回执语言状态超过保存限制；所有原稿已保留。')
        if old_raw == new_raw:
            return before, before, sorted(stale)
        def require_locale():
            require_index()
            if (self._local_versions(root, identifier, language) != before
                    or self.dev_room._locale_raw(root, identifier)[0] != old_raw
                    or self.dev_room._matched_catalog(current, self.dev_room._catalog()) != entry):
                raise DevRoomSyncConflict('核对回执期间本地语言或目录已改变，未覆盖稿件。', 'console_changed', accepted=True)
        operation['localeExpiry'] = {'appliedUnityRevision': source['revision'], 'before': before,
                   'afterLocaleRawSha256': _sha(new_raw), 'staleLanguages': sorted(stale)}
        # Durable write-ahead evidence makes a sidecar/index failure recoverable
        # without treating our metadata-only expiry as a later user edit.
        self._write_json(root, (*OPERATION_PARTS, operation['requestId'] + '.json'), operation,
                         before_replace=require_locale)
        if old_raw is not None:
            history = (*DEV_ROOM_PARTS, '.history', identifier, 'locales', _sha(old_raw) + '.json')
            self.dev_room._mkdir(root, *history[:-1])
            path = self.dev_room._checked_path(root, *history)
            if path.exists():
                if path.read_bytes() != old_raw:
                    raise ValueError('回执语言历史校验失败，原稿已保留。')
            else:
                self.dev_room._atomic_write(root, history, old_raw, before_replace=require_locale)
        self.dev_room._mkdir(root, *DEV_ROOM_PARTS, '.locales')
        self.dev_room._atomic_write(root, (*DEV_ROOM_PARTS, '.locales', identifier + '.json'), new_raw,
                                   before_replace=require_locale)
        return before, self._local_versions(root, identifier, language), sorted(stale)

    def receipt(self, expectedRoot, requestId):
        self._require_source_sync()
        _request_id(requestId)
        with self.dev_room._scope(expectedRoot) as root:
            operation = self._operation(root, requestId)
            if not operation:
                return {'requestId': requestId, 'status': 'not_submitted', 'accepted': False, 'code': 'request_unknown'}
            if operation['kind'] != 'push' or operation['status'] in {'applied', 'unchanged', 'failed', 'conflict'}:
                return self._public(operation)
            with self._index_lock(root):
                operation = self._operation(root, requestId)
                path = self._bridge_path('receipts', requestId + '.json')
                if not path.exists():
                    return {'requestId': requestId, 'documentId': operation['documentId'], 'language': operation.get('language'),
                            'status': 'pending' if operation['status'] == 'pending' else 'unknown', 'accepted': True}
                with path.open('rb') as receipt_file:
                    raw = receipt_file.read(MAX_OPERATION_BYTES + 1)
                if len(raw) > MAX_OPERATION_BYTES:
                    raise ValueError('Unity 同步回执超过限制。')
                try:
                    receipt = json.loads(raw.decode('utf-8'), object_pairs_hook=self.sources._unique_json)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError('Unity 回执无法核对，原请求已保留。') from exc
                request = operation.get('request')
                if not request or request.get('schemaVersion') != 2:
                    raise DevRoomSyncConflict('旧版在途请求保留待核对，不能自动重送。', 'legacy_pending', accepted=True)
                keys = ('schemaVersion', 'requestId', 'editorInstanceNonce', 'projectId', 'projectLibraryGuid', 'documentId',
                        'consoleRevision', 'contentSha256', 'expectedLibrary', 'document')
                if (not isinstance(receipt, dict) or any(receipt.get(k) != request[k] for k in keys)
                        or receipt.get('requestSha256') != _sha(_json_bytes(request))):
                    raise DevRoomSyncConflict('回执与原请求身份、语言版本或完整内容不匹配。', 'receipt_mismatch', accepted=True)
                state = receipt.get('status')
                if state in {'failed', 'conflict'}:
                    return self._finish(root, operation, state, message=receipt.get('message', ''))
                if state in {'pending', 'unknown'}:
                    return {'requestId': requestId, 'status': state, 'accepted': True, 'message': receipt.get('message', '')}
                if (state != 'applied' or not isinstance(receipt.get('actual'), dict)
                        or receipt.get('appliedContentSha256') != request['contentSha256']
                        or self.sources.document_content_revision(receipt['actual']) != request['contentSha256']):
                    raise DevRoomSyncConflict('Editor 尚未返回可核对的实际完成内容。', 'receipt_mismatch', accepted=True)
                actual_sections = receipt['actual'].get('sections', [])
                if len(actual_sections) != len(request['target']['sections']):
                    raise DevRoomSyncConflict('实际完成章节数量不一致。', 'receipt_mismatch', accepted=True)
                for desired, actual in zip(request['target']['sections'], actual_sections):
                    wanted, found = desired.get('image', {}), actual.get('image', {})
                    if wanted.get('stagingName'):
                        final_path = 'Assets/Resources/UI/DevsRealm/ConsoleMedia/' + wanted['stagingName']
                        matches = (found.get('assetPath') == final_path and found.get('sha256') == wanted['sha256']
                                   and _GUID.fullmatch(str(found.get('guid', '')))
                                   and type(found.get('fileID')) is int and found['fileID'] > 0
                                   and found.get('type') == 3 and _SHA.fullmatch(str(found.get('metaRevision', ''))))
                    else:
                        matches = all((found.get(k) or (0 if k in {'fileID', 'type'} else '')) ==
                                      (wanted.get(k) or (0 if k in {'fileID', 'type'} else ''))
                                      for k in ('guid', 'fileID', 'type', 'assetPath', 'sha256', 'metaRevision'))
                    if not matches:
                        raise DevRoomSyncConflict('实际图片绑定与确认请求不一致。', 'receipt_mismatch', accepted=True)
                inventory = self._inventory()
                index, index_revision = self._index(root, inventory)
                binding = index['bindings'].get(operation['documentId'])
                if not binding:
                    raise DevRoomSyncConflict('原文档绑定已改变，完成回执保留。', 'source_changed', accepted=True)
                source = self._source(inventory, binding)
                if (source['revision'] != receipt.get('appliedUnityRevision')
                        or source['metaRevision'] != receipt.get('appliedMetaRevision')
                        or source['structureRevision'] != receipt.get('appliedStructureRevision')
                        or source['mediaRevision'] != receipt.get('appliedMediaRevision')
                        or source['contentRevision'] != request['contentSha256']
                        or source['expectedLibrary']['revision'] != receipt.get('appliedLibraryRevision')
                        or source['expectedLibrary']['metaRevision'] != receipt.get('appliedLibraryMetaRevision')):
                    raise DevRoomSyncConflict('实际游戏文件或图片与完成回执不一致，未标完成。', 'receipt_source_changed', accepted=True)
                if self.sources.document_media_revision(receipt['actual']) != source['mediaRevision']:
                    raise DevRoomSyncConflict('实际游戏图片引用与完成回执不一致。', 'receipt_source_changed', accepted=True)
                def require_index():
                    self.dev_room._check_current_root(root)
                    if self._read_json(root, INDEX_PARTS)[1] != index_revision:
                        raise DevRoomSyncConflict('回执核对期间来源绑定已有修改，未覆盖。', 'source_changed', accepted=True)
                try:
                    with self.dev_room._write_lock(root):
                        observed, after, stale = self._reconcile_applied_languages(root, operation, request, source, require_index)
                        new_binding = self._binding(root, inventory, source, operation['language'], requestId,
                                                    console_revision=request['consoleRevision'])
                        local_changed = observed != operation['localVersions']
                        if local_changed:
                            new_binding['lastConsoleRevision'] = operation['localVersions']['sourceRevision']
                            new_binding['lastLocaleRawSha256'] = operation['localVersions']['localeRawSha256']
                        index['schemaVersion'] = 2
                        index['bindings'][operation['documentId']] = new_binding
                        def require_versions():
                            require_index()
                            if self._local_versions(root, operation['documentId'], operation['language']) != after:
                                raise DevRoomSyncConflict('回执提交期间语言稿已有修改，未覆盖。', 'console_changed', accepted=True)
                        self._write_json(root, INDEX_PARTS, index, before_replace=require_versions)
                        return self._finish(root, operation, 'applied', unityRevision=source['revision'],
                            appliedContentSha256=request['contentSha256'], processedAt=receipt.get('processedAt', ''),
                            localChangedSincePush=local_changed, staleLanguages=stale)
                except Exception as exc:
                    try:
                        self._finish(root, operation, 'unknown', error=str(exc), code=getattr(exc, 'code', 'receipt_commit_failed'),
                                     gameAppliedVerified=True)
                    except OSError:
                        pass
                    exc.accepted = True; exc.syncRequestId = requestId
                    raise
