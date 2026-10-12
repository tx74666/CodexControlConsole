"""Read bounded, typed Unity Dev Room sources and round-trip fixed-slot content.

This module never starts Unity or writes any Unity asset. Image references and
source identity stay fixed; explicit image metadata may accompany locale text.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken
from dev_room_media import MAX_MEDIA_BYTES, inspect_image, object_name


LIBRARY_PATH = 'Assets/Resources/DevsRealm/DocumentLibrary.asset'
DOCUMENT_ROOTS = ('Assets/GameData/DevsRealm/Documents', 'Assets/Resources/DevsRealm/Documents')
LIBRARY_SCRIPT_GUID = '026e4b7ddfbd92444bc58793e45a5887'
DOCUMENT_SCRIPT_GUID = '5327acab2ec386345b106b76a7532194'
MAX_ASSET_BYTES = 1024 * 1024
MAX_META_BYTES = 64 * 1024
MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
MAX_BODY_BYTES = 512 * 1024
MAX_DOCUMENTS = 256
MAX_SECTIONS = 128
MAX_SOURCE_ENTRIES = 2048
_MARKER = '<!-- rr-dev-room:'
MEDIA_MARKER = '<!-- codex-dev-room-media '
_GUID = re.compile(r'[0-9a-f]{32}')
_ID = re.compile(r'[a-z][a-z0-9-]{0,127}')


class UnityDocumentError(ValueError):
    pass


class UnitySourceConflict(UnityDocumentError):
    pass


class _UnityLoader(yaml.SafeLoader):
    pass


# Unity writes yyyy-MM-dd as an ordinary string. Avoid implicit timestamp
# conversion without changing PyYAML's global loaders or other components.
_UnityLoader.yaml_implicit_resolvers = {
    key: [(tag, expression) for tag, expression in rules if tag != 'tag:yaml.org,2002:timestamp']
    for key, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _unique_mapping(loader, node, deep=False):
    if not isinstance(node, yaml.MappingNode):
        raise UnityDocumentError('Unity 文档映射格式无效。')
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise UnityDocumentError('Unity 文档包含重复或无效字段。')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UnityLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _integer(value, label, minimum=0, maximum=2 ** 63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise UnityDocumentError(f'{label}无效。')
    return value


def _text(value, label, *, maximum=MAX_BODY_BYTES, empty=True, heading=False):
    if value is None and empty:
        value = ''
    if not isinstance(value, str) or not empty and not value.strip():
        raise UnityDocumentError(f'{label}无效。')
    try:
        if len(value.encode('utf-8')) > maximum:
            raise UnityDocumentError(f'{label}超过读取限制。')
    except UnicodeError as exc:
        raise UnityDocumentError(f'{label}包含无效文字。') from exc
    if any(ord(char) < 32 and char not in '\t\r\n' or ord(char) == 127 for char in value):
        raise UnityDocumentError(f'{label}包含无效控制字符。')
    if heading and (len(value) > 200 or any(char in value for char in '\r\n\t')):
        raise UnityDocumentError(f'{label}须为不超过 200 字的一行文字。')
    return value


def _guid(value, label):
    if not isinstance(value, str) or not _GUID.fullmatch(value):
        raise UnityDocumentError(f'{label}无效。')
    return value


def _source_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise UnityDocumentError('Unity 文档内容身份无效。')
    return value


def _date(value, label, *, empty=False):
    value = _text(value, label, maximum=32, empty=empty)
    if not value and empty:
        return value
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        date.fromisoformat(value)
    except ValueError as exc:
        raise UnityDocumentError(f'{label}须为 yyyy-MM-dd。') from exc
    return value


def _source_date(value):
    value = _text(value, '原来源更新日期', maximum=64)
    if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T[0-9:.]+Z)?', value):
        raise UnityDocumentError('原来源更新日期须为日期或 UTC 时间。')
    return value


def _link_or_reparse(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _workspace(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise UnityDocumentError('请指定 Unity 工作区。')
    candidate = Path(value)
    if not candidate.is_absolute() or str(candidate).startswith('\\\\'):
        raise UnityDocumentError('Unity 工作区须为本机完整路径。')
    for component in (candidate, *candidate.parents):
        if _link_or_reparse(component):
            raise UnityDocumentError('Unity 工作区路径不能含链接。')
    root = candidate.resolve()
    if not root.is_dir():
        raise UnityDocumentError('Unity 工作区不存在。')
    version, _ = _read(root, 'ProjectSettings/ProjectVersion.txt', 4096)
    if not re.search(rb'^m_EditorVersion: [0-9][^\r\n]*\r?$', version, re.M):
        raise UnityDocumentError('此路径不是可识别的 Unity 工作区。')
    return root


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or any(char in value for char in ':?#%')
            or any(ord(char) < 32 for char in value)):
        raise UnityDocumentError('Unity 相对路径无效。')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {'', '.', '..'} for part in value.split('/')):
        raise UnityDocumentError('Unity 路径不能离开所选工作区。')
    return path


def _path(root, relative):
    parts = _relative(relative).parts
    current = root
    if _link_or_reparse(root):
        raise UnityDocumentError('Unity 工作区路径不能含链接。')
    for part in parts:
        current = current / part
        if _link_or_reparse(current):
            raise UnityDocumentError('Unity 文档路径不能含链接。')
    if not current.resolve().is_relative_to(root):
        raise UnityDocumentError('Unity 文档路径不能离开所选工作区。')
    return current


def _read(root, relative, maximum):
    path = _path(root, relative)
    if not path.is_file():
        raise UnityDocumentError('Unity 文档来源不是普通文件。')
    with path.open('rb') as source:
        raw = source.read(maximum + 1)
    if len(raw) > maximum:
        raise UnityDocumentError('Unity 文档来源超过读取限制。')
    return raw, _hash(raw)


def _meta(root, relative):
    raw, revision = _read(root, relative, MAX_META_BYTES)
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise UnityDocumentError('Unity 来源 metadata 编码无效。') from exc
    matches = re.findall(r'^guid: ([0-9a-f]{32})\r?$', text, re.M)
    if len(matches) != 1:
        raise UnityDocumentError('Unity 来源 metadata 须包含唯一 GUID。')
    return matches[0], revision


def _asset(root, relative, class_name, script_guid):
    raw, revision = _read(root, relative, MAX_ASSET_BYTES)
    try:
        text = raw.decode('utf-8-sig')
        header = re.match(r'\A%YAML 1\.1\r?\n%TAG !u! tag:unity3d\.com,2011:\r?\n--- !u!114 &11400000\r?\n', text)
        if not header:
            raise UnityDocumentError('Unity 文档来源须为独立的 ScriptableObject 文字资产。')
        payload = text[header.end():]
        for index, token in enumerate(yaml.scan(payload, Loader=_UnityLoader)):
            if index > 150000 or isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise UnityDocumentError('Unity 文档不支持 YAML 链接或自定义标签。')
        value = yaml.load(payload, Loader=_UnityLoader)
    except (UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise UnityDocumentError('Unity 文档来源格式无效。') from exc
    if not isinstance(value, dict) or set(value) != {'MonoBehaviour'} or not isinstance(value['MonoBehaviour'], dict):
        raise UnityDocumentError('Unity 文档资产结构无效。')
    value = value['MonoBehaviour']
    script = value.get('m_Script')
    if (not isinstance(script, dict) or script.get('guid') != script_guid or script.get('fileID') != 11500000
            or value.get('m_EditorClassIdentifier') != 'Unity.RandomRealm.Gameplay.Builds::Unity.RandomRealm.Gameplay.' + class_name):
        raise UnityDocumentError('Unity 文档资产类型与当前项目不符。')
    return value, revision


def _index_document_metas(root):
    """Only visit the two existing document roots; never scan the project."""
    result, seen, pending, count = {}, set(), [(item, 0) for item in DOCUMENT_ROOTS], 0
    while pending:
        relative, depth = pending.pop()
        if depth > 8:
            raise UnityDocumentError('Unity 文档目录层级超过限制。')
        directory = _path(root, relative)
        if not directory.is_dir():
            raise UnityDocumentError('Unity 文档目录不存在。')
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_SOURCE_ENTRIES:
                    raise UnityDocumentError('Unity 文档目录超过读取限制。')
                item_relative = relative + '/' + entry.name
                if entry.is_dir(follow_symlinks=False) or entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400:
                    checked = _path(root, item_relative)
                    if checked.is_dir():
                        pending.append((item_relative, depth + 1))
                    continue
                if not entry.name.endswith('.asset.meta'):
                    continue
                guid, revision = _meta(root, item_relative)
                if guid in seen:
                    raise UnityDocumentError('Unity 文档目录包含重复 GUID。')
                seen.add(guid)
                result[guid] = (item_relative[:-5], revision)
                if len(result) > MAX_DOCUMENTS:
                    raise UnityDocumentError('Unity 文档数量超过读取限制。')
    return result


def _image(value):
    if not isinstance(value, dict) or set(value) - {'fileID', 'guid', 'type'} or 'fileID' not in value:
        raise UnityDocumentError('Unity 文档图片引用无效。')
    file_id = _integer(value['fileID'], '图片 fileID', minimum=0)
    if file_id == 0 and set(value) != {'fileID'}:
        raise UnityDocumentError('Unity 空图片引用无效。')
    if file_id != 0:
        _guid(value.get('guid'), '图片 GUID')
        _integer(value.get('type'), '图片类型', maximum=3)
    return dict(value)


def _document(asset, path, guid, revision, meta_revision):
    category = _integer(asset.get('m_Category'), '文档分类', maximum=4)
    raw_sections = asset.get('m_Sections')
    if not isinstance(raw_sections, list) or not 1 <= len(raw_sections) <= MAX_SECTIONS:
        raise UnityDocumentError('Unity 文档须有完整有序章节。')
    sections = []
    for index, section in enumerate(raw_sections):
        if not isinstance(section, dict):
            raise UnityDocumentError('Unity 文档章节结构无效。')
        resource = _text(section.get('m_ImageResourcePath'), '图片 Resources 路径', maximum=2048)
        if resource:
            _relative(resource)
        sections.append({'index': index,
            'title': _text(section.get('m_Title'), '章节标题', empty=False, heading=True),
            'body': _text(section.get('m_Body'), '章节正文', empty=False),
            'image': _image(section.get('m_Image')),
            'imageResourcePath': resource,
            'imageCaption': _text(section.get('m_ImageCaption'), '图片说明', maximum=64 * 1024)})
    result = {'id': _source_id(asset.get('m_Id')), 'guid': guid, 'path': path, 'localFileId': 11400000,
        'title': _text(asset.get('m_Title'), '文档标题', empty=False, heading=True),
        'summary': _text(asset.get('m_Summary'), '文档摘要', empty=False, maximum=64 * 1024),
        'category': category, 'order': _integer(asset.get('m_DisplayOrder'), '文档顺序', maximum=100000),
        'updatedAt': _date(asset.get('m_UpdatedAt'), '文档更新日期'),
        'sourceReference': _text(asset.get('m_SourceReference'), '文档来源说明', maximum=64 * 1024),
        'sourceUpdatedAt': _source_date(asset.get('m_SourceUpdatedAt')),
        'revision': revision, 'metaRevision': meta_revision, 'sections': sections}
    return result


def read_inventory(workspace):
    root = _workspace(workspace)
    library_guid, library_meta_revision = _meta(root, LIBRARY_PATH + '.meta')
    library, library_revision = _asset(root, LIBRARY_PATH, 'DevsRealmDocumentLibraryAsset', LIBRARY_SCRIPT_GUID)
    raw_categories = library.get('m_Categories')
    if not isinstance(raw_categories, list) or not 1 <= len(raw_categories) <= 5:
        raise UnityDocumentError('Unity 文档分类列表无效。')
    categories, category_ids = [], set()
    for category in raw_categories:
        if not isinstance(category, dict):
            raise UnityDocumentError('Unity 文档分类无效。')
        id = _integer(category.get('m_Category'), '分类身份', maximum=4)
        if id in category_ids:
            raise UnityDocumentError('Unity 文档分类身份重复。')
        category_ids.add(id)
        categories.append({'id': id, 'order': _integer(category.get('m_DisplayOrder'), '分类顺序', maximum=100000),
            'title': _text(category.get('m_Title'), '分类标题', empty=False, heading=True),
            'summary': _text(category.get('m_Summary'), '分类说明', empty=False, maximum=64 * 1024)})
    categories.sort(key=lambda item: item['order'])
    references = library.get('m_Documents')
    if not isinstance(references, list) or not 1 <= len(references) <= MAX_DOCUMENTS:
        raise UnityDocumentError('Unity 文档库引用列表无效。')
    index = _index_document_metas(root)
    documents, source_ids, source_guids = [], set(), set()
    for reference in references:
        if (not isinstance(reference, dict) or set(reference) != {'fileID', 'guid', 'type'}
                or reference['fileID'] != 11400000 or reference['type'] != 2):
            raise UnityDocumentError('Unity 文档库包含无效引用。')
        guid = _guid(reference['guid'], '文档 GUID')
        if guid in source_guids:
            raise UnityDocumentError('Unity 文档库引用了重复资产。')
        source_guids.add(guid)
        if guid not in index:
            raise UnityDocumentError('Unity 文档库引用未找到，或位于允许的文档目录之外。')
        path, meta_revision = index[guid]
        asset, revision = _asset(root, path, 'DevsRealmDocumentAsset', DOCUMENT_SCRIPT_GUID)
        document = _document(asset, path, guid, revision, meta_revision)
        if document['id'] in source_ids or document['category'] not in category_ids:
            raise UnityDocumentError('Unity 文档内容身份重复，或分类不存在。')
        source_ids.add(document['id'])
        documents.append(document)
    category_order = {item['id']: index for index, item in enumerate(categories)}
    documents.sort(key=lambda item: (category_order[item['category']], item['order']))
    # Reject a torn snapshot, including GUID metadata changed midway through a
    # read. This small second pass stays inside the already selected 16 assets.
    check_files = [(LIBRARY_PATH, library_revision, MAX_ASSET_BYTES),
                   (LIBRARY_PATH + '.meta', library_meta_revision, MAX_META_BYTES)]
    for document in documents:
        check_files.extend(((document['path'], document['revision'], MAX_ASSET_BYTES),
                            (document['path'] + '.meta', document['metaRevision'], MAX_META_BYTES)))
    for path, revision, maximum in check_files:
        if _read(root, path, maximum)[1] != revision:
            raise UnitySourceConflict('Unity 文档读取期间发生变化，请重新读取。')
    for document in documents:
        document['scope'] = 'globalLibrary'
    identity_root = os.path.normcase(str(root)).rstrip('\\/')
    project_id = _hash(('unity-dev-room-v1\n' + identity_root + '\n' + library_guid).encode('utf-8'))
    inventory_revision = _hash(json.dumps(check_files, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    library_source = {'kind': 'devRoomLibrary', 'path': LIBRARY_PATH, 'guid': library_guid,
                      'revision': library_revision, 'metaRevision': library_meta_revision}
    for document in documents:
        document['expectedLibrary'] = dict(library_source)
    documents.extend(read_owned_display_documents(root, resolve_media=False))
    known_identities = _known_texture_identities(documents)
    for document in documents:
        resolve_document_media(root, document, known_texture_ids=known_identities)
    return {'workspace': str(root), 'identityRoot': identity_root, 'projectId': project_id,
        'revision': inventory_revision,
        'library': {'kind': 'devRoomLibrary', 'path': LIBRARY_PATH, 'guid': library_guid, 'revision': library_revision,
                    'metaRevision': library_meta_revision}, 'categories': categories, 'documents': documents}


def document_content_revision(document):
    """v2 content hash: text, captions, resource references and actual pixels."""
    if not isinstance(document, dict):
        raise UnityDocumentError('文档文字结构无效。')
    digest = hashlib.sha256()
    def append(value, label):
        raw = _text(value, label, empty=True).encode('utf-8')
        digest.update(struct.pack('>I', len(raw)))
        digest.update(raw)
    append(document.get('title'), '文档标题')
    append(document.get('summary'), '文档摘要')
    sections = document.get('sections')
    if not isinstance(sections, list) or not 1 <= len(sections) <= MAX_SECTIONS:
        raise UnityDocumentError('文档章节结构无效。')
    digest.update(struct.pack('>I', len(sections)))
    for index, section in enumerate(sections):
        if not isinstance(section, dict) or section.get('index') != index:
            raise UnityDocumentError('文档章节 index 不能重排。')
        append(section.get('title'), '章节标题')
        append(section.get('body'), '章节正文')
        append(section.get('imageCaption', ''), '图片说明')
        image = section.get('image', {})
        append(image.get('resourcePath', ''), '图片 Resources 路径')
        append(image.get('sha256', ''), '图片像素身份')
    return digest.hexdigest()


def _editable_fields(document):
    if not isinstance(document, dict):
        raise UnityDocumentError('文档文字结构无效。')
    _source_id(document.get('id'))
    _guid(document.get('guid'), '文档 GUID')
    _text(document.get('title'), '文档标题', empty=False, heading=True)
    _text(document.get('summary'), '文档摘要', empty=False, maximum=64 * 1024)
    document_content_revision(document)
    fields = [document['title'], document['summary']]
    for section in document['sections']:
        _text(section['title'], '章节标题', empty=False, heading=True)
        fields.extend((section['title'], section['body'], section.get('imageCaption', '')))
    if any(_MARKER in value for value in fields):
        raise UnityDocumentError('正文不能含 Dev Room 保留的同步注释。')


def document_to_markdown(document, *, include_media=False):
    _editable_fields(document)
    identity = json.dumps({'id': document['id'], 'guid': document['guid']}, ensure_ascii=False, separators=(',', ':'))
    result = f'{_MARKER}v1 {identity} -->\n# {document["title"]}\n\n'
    result += f'{_MARKER}summary -->\n{document["summary"]}\n{_MARKER}summary-end -->\n\n'
    for section in document['sections']:
        index = section['index']
        media = media_to_json(section)
        result += (f'{_MARKER}section {index} -->\n## {section["title"]}\n{section["body"]}\n'
                   + (f'{MEDIA_MARKER}{media} -->\n' if include_media else '') +
                   f'{_MARKER}section-end {index} -->\n\n')
    if len(result.encode('utf-8')) > MAX_MARKDOWN_BYTES:
        raise UnityDocumentError('文档 Markdown 超过读取限制。')
    return result


def markdown_to_document(markdown, baseline):
    """Edit only title/summary/ordered section text; retain every sidecar field."""
    _editable_fields(baseline)
    markdown = _text(markdown, '文档 Markdown', maximum=MAX_MARKDOWN_BYTES, empty=False)
    first, separator, remainder = markdown.partition('\n')
    newline = '\r\n' if first.endswith('\r') else '\n'
    if newline == '\r\n':
        first = first[:-1]
    if not separator or not first.startswith(_MARKER + 'v1 ') or not first.endswith(' -->'):
        raise UnityDocumentError('请保留 Markdown 顶部的文档来源注释。')
    try:
        identity = json.loads(first[len(_MARKER + 'v1 '):-4])
    except ValueError as exc:
        raise UnityDocumentError('Markdown 文档来源注释无效。') from exc
    if identity != {'id': baseline['id'], 'guid': baseline['guid']}:
        raise UnityDocumentError('Markdown 文档来源身份已改变，不能回写其他资产。')
    endline = re.escape(newline)
    prefix = re.match(r'\A# ([^\r\n]+)' + endline * 2 + re.escape(_MARKER + 'summary -->') + endline
                      + r'(.*?)' + endline + re.escape(_MARKER + 'summary-end -->') + endline * 2, remainder, re.S)
    if not prefix:
        raise UnityDocumentError('Markdown 文档标题或摘要结构有误，请保留同步注释。')
    updated = deepcopy(baseline)
    updated['title'], updated['summary'] = prefix.group(1), prefix.group(2)
    remainder = remainder[prefix.end():]
    for index, section in enumerate(updated['sections']):
        expression = (re.escape(_MARKER + f'section {index} -->') + endline + r'## ([^\r\n]+)' + endline
                      + r'(.*?)' + endline + re.escape(_MARKER + f'section-end {index} -->') + endline * 2)
        match = re.match(expression, remainder, re.S)
        if not match:
            raise UnityDocumentError('Markdown 章节数量或 index 已改变，请保留原有章节顺序。')
        section['title'], section['body'] = match.group(1), match.group(2)
        section['body'], media = split_media(section['body'], index)
        if media is not None:
            section['image'] = validate_image_edit(media, section)
            section['imageCaption'] = _text(media.get('imageCaption'), '图片说明', maximum=64 * 1024)
        remainder = remainder[match.end():]
    if remainder:
        raise UnityDocumentError('Markdown 末尾存在未识别内容，未回写 Unity。')
    _editable_fields(updated)
    updated['contentRevision'] = document_content_revision(updated)
    return updated


def _length_hash(strings, count=None):
    digest = hashlib.sha256()
    for value in strings:
        if value is None:
            digest.update(struct.pack('>I', count))
        else:
            raw = str(value).encode('utf-8')
            digest.update(struct.pack('>I', len(raw)))
            digest.update(raw)
    return digest.hexdigest()


def document_structure_revision(document):
    fields = [document['id'], document['guid'], str(document.get('localFileId', 11400000)),
              str(document['category']), str(document['order']), None]
    for section in document['sections']:
        fields.extend((str(section['index']), 'section'))
    return _length_hash(fields, len(document['sections']))


def document_media_revision(document):
    fields = [None]
    for section in document['sections']:
        image = section['image']
        fields.extend((image.get('guid') or '', str(image.get('fileID') or 0), str(image.get('type') or 0),
                       image.get('resourcePath') or '', image.get('assetPath') or '', image.get('sha256') or '',
                       image.get('metaRevision') or ''))
    return _length_hash(fields, len(document['sections']))


def _known_texture_identities(documents):
    """Direct references in the verified document Texture2D slots, never guesses."""
    identities = {}
    for document in documents:
        for section in document['sections']:
            image = section['image']
            if image.get('guid') and image.get('fileID', 0) > 0 and image.get('type') == 3:
                identities.setdefault(image['guid'], set()).add(image['fileID'])
    return {guid: next(iter(file_ids)) for guid, file_ids in identities.items() if len(file_ids) == 1}


def _resolve_image(root, reference, resource, image_bindings=None, known_texture_ids=None):
    """Resolve only explicit Resources paths or a small existing image root.

    No project/Library/Temp traversal occurs. Non-Resources references must be in
    the DevsRealm image root or an explicit registered document binding.
    """
    reference = _image(reference)
    if reference.get('fileID', 0) == 0 and not resource:
        return {'guid': '', 'fileID': 0, 'type': 0, 'resourcePath': '',
                'assetPath': '', 'sha256': '', 'stagingName': '', 'metaRevision': ''}
    candidates = []
    if reference.get('guid') and image_bindings and reference['guid'] in image_bindings:
        explicit = image_bindings[reference['guid']]
        if not isinstance(explicit, str) or not explicit.startswith('Assets/') or not explicit.lower().endswith(('.png', '.jpg', '.jpeg')):
            raise UnityDocumentError('显式图片绑定无效。')
        _path(root, explicit)
        candidates.append(explicit)
    if resource:
        _relative(resource)
        for extension in ('png', 'jpg', 'jpeg'):
            relative = 'Assets/Resources/' + resource + '.' + extension
            try:
                path = _path(root, relative)
            except FileNotFoundError:
                continue
            if path.is_file():
                if relative not in candidates:
                    candidates.append(relative)
    if not candidates and reference.get('guid'):
        pending, count = [(relative, 0) for relative in
                           ('Assets/Resources/UI/DevsRealm', 'Assets/Art/Images/UI/DevsRealm')], 0
        while pending:
            directory, depth = pending.pop()
            if depth > 8:
                raise UnityDocumentError('图片目录层级超过限制。')
            try:
                checked = _path(root, directory)
            except FileNotFoundError:
                continue
            with os.scandir(checked) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_SOURCE_ENTRIES:
                        raise UnityDocumentError('图片目录超过读取限制。')
                    item = directory + '/' + entry.name
                    checked_item = _path(root, item)
                    if checked_item.is_dir():
                        pending.append((item, depth + 1))
                    elif entry.name.lower().endswith(('.png.meta', '.jpg.meta', '.jpeg.meta')):
                        if _meta(root, item)[0] == reference['guid']:
                            candidates.append(item[:-5])
    if len(candidates) != 1:
        raise UnityDocumentError('图片引用没有唯一的允许来源，不能展示或同步。')
    relative = candidates[0]
    guid, meta_revision = _meta(root, relative + '.meta')
    if reference.get('guid') and reference['guid'] != guid:
        raise UnitySourceConflict('图片 GUID 与 Resources 路径不一致。')
    raw, revision = _read(root, relative, MAX_MEDIA_BYTES)
    metadata = inspect_image(raw)
    if _read(root, relative + '.meta', MAX_META_BYTES)[1] != meta_revision:
        raise UnitySourceConflict('图片 metadata 在读取时发生变化。')
    resolved_reference = dict(reference)
    identity_resolved = True
    if reference.get('fileID', 0) == 0:
        meta_raw = _read(root, relative + '.meta', MAX_META_BYTES)[0]
        try:
            importer_is_texture = len(re.findall(r'^TextureImporter:\s*$', meta_raw.decode('utf-8-sig'), re.M)) == 1
        except UnicodeError as exc:
            raise UnityDocumentError('图片 importer metadata 编码无效。') from exc
        known_id = (known_texture_ids or {}).get(guid)
        identity_resolved = importer_is_texture and type(known_id) is int and known_id > 0
        # The source's Resources fallback is real, but its local ID can only be
        # copied from a known typed reference. An empty table is not evidence.
        resolved_reference = {'guid': guid, 'fileID': known_id if identity_resolved else 0, 'type': 3}
    result = {'guid': resolved_reference.get('guid', ''), 'fileID': resolved_reference.get('fileID', 0),
            'type': resolved_reference.get('type', 0), 'resourcePath': resource, 'assetPath': relative,
            'sha256': revision, 'stagingName': '', 'metaRevision': meta_revision,
            'mimeType': metadata['mimeType'], 'size': metadata['size']}
    if not identity_resolved:
        result.update(identityResolved=False, identityWarning='Resources 图片缺少可核对的 Texture2D local fileID；保留浏览，回写尚不可用。')
    return result


def resolve_document_media(root, document, image_bindings=None, known_texture_ids=None):
    document['writebackSupported'] = True
    for section in document['sections']:
        section['image'] = _resolve_image(root, section['image'], section.get('imageResourcePath', ''), image_bindings, known_texture_ids)
        if section['image'].get('identityResolved') is False:
            document['writebackSupported'] = False
    document['contentRevision'] = document_content_revision(document)
    document['structureRevision'] = document_structure_revision(document)
    document['mediaRevision'] = document_media_revision(document)
    return document


def media_to_json(section):
    image = section['image']
    value = {key: image.get(key, '') for key in
             ('sha256', 'stagingName', 'resourcePath', 'guid', 'assetPath')}
    value.update(section=section['index'], imageCaption=section.get('imageCaption', ''),
                 fileID=image.get('fileID', 0), type=image.get('type', 0))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e')


def split_media(body, index):
    match = re.search(r'(?:\r?\n)?' + re.escape(MEDIA_MARKER) + r'([^\r\n]*) -->\Z', body)
    if not match:
        if MEDIA_MARKER in body:
            raise UnityDocumentError('图片元数据位置或格式无效。')
        return body, None
    if MEDIA_MARKER in body[:match.start()]:
        raise UnityDocumentError('同一章节包含重复图片元数据。')
    try:
        value = json.loads(match.group(1), object_pairs_hook=_unique_json)
    except (ValueError, TypeError) as exc:
        raise UnityDocumentError('图片元数据格式无效。') from exc
    if not isinstance(value, dict) or value.get('section') != index:
        raise UnityDocumentError('图片元数据章节身份已改变。')
    return body[:match.start()], value


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('重复JSON字段。')
        result[key] = value
    return result


def validate_image_edit(value, baseline_section):
    required = {'section', 'imageCaption', 'sha256', 'stagingName', 'resourcePath',
                'guid', 'fileID', 'type', 'assetPath'}
    if set(value) != required or value['section'] != baseline_section['index']:
        raise UnityDocumentError('图片元数据字段或章节身份无效。')
    caption = _text(value['imageCaption'], '图片说明', maximum=64 * 1024)
    if '-->' in caption or MEDIA_MARKER in caption:
        raise UnityDocumentError('图片说明不能包含保留的元数据注释。')
    image = {key: value[key] for key in required - {'section', 'imageCaption'}}
    for key in ('sha256', 'stagingName', 'resourcePath', 'guid', 'assetPath'):
        if not isinstance(image[key], str):
            raise UnityDocumentError('图片元数据无效。')
    _integer(image['fileID'], '图片 fileID')
    _integer(image['type'], '图片类型', maximum=3)
    if image['stagingName']:
        name = object_name(image['stagingName'])
        final_path = 'Assets/Resources/UI/DevsRealm/ConsoleMedia/' + name
        if (name.split('.')[0] != image['sha256'] or image['guid'] or image['fileID'] != 0
                or image['type'] != 3 or image['assetPath'] not in ('', final_path)
                or image['resourcePath'] != 'UI/DevsRealm/ConsoleMedia/' + image['sha256']):
            raise UnityDocumentError('待导入图片身份无效。')
        # Early unsubmitted drafts stored an empty destination. Derive only the
        # exact SHA filename for those tokens; retain the saved body unchanged.
        image['assetPath'] = final_path
        original = baseline_section['image']
        if (original.get('sha256') == image['sha256'] and original.get('assetPath') == final_path
                and original.get('resourcePath') == image['resourcePath']):
            # A receipt may have promoted this immutable object into a real
            # Unity texture. Preserve the saved body, but use its actual binding.
            image = deepcopy(original)
    else:
        original = baseline_section['image']
        if any(image[key] != original.get(key, '' if key not in {'fileID', 'type'} else 0)
               for key in image):
            raise UnityDocumentError('既有图片来源不能改成任意路径；替换请使用图片上传。')
        image['metaRevision'] = original.get('metaRevision', '')
    return image


def read_bound_document(workspace, relative, guid, local_file_id=11400000, image_bindings=None, *, resolve_media=True):
    """Read an explicitly chosen stand-alone or subasset document without scan.

    Display-owned documents share the parent GUID/path, so stable localFileId is
    mandatory. Membership is verified by the Editor bridge before writes.
    """
    root = _workspace(workspace)
    if not _relative(relative).parts[0] == 'Assets' or not relative.endswith('.asset'):
        raise UnityDocumentError('显式文档来源必须是 Assets 内的 .asset。')
    expected_guid = _guid(guid, '文档 GUID')
    _integer(local_file_id, '文档 local fileID', minimum=1)
    actual_guid, meta_revision = _meta(root, relative + '.meta')
    if expected_guid != actual_guid:
        raise UnitySourceConflict('显式文档 GUID 已改变。')
    raw, revision = _read(root, relative, MAX_ASSET_BYTES)
    try:
        text = raw.decode('utf-8-sig')
        blocks = re.split(r'^--- !u!(\d+) &(\d+)\r?\n', text, flags=re.M)
        matches = []
        for offset in range(1, len(blocks), 3):
            if blocks[offset] != '114' or int(blocks[offset + 1]) != local_file_id:
                continue
            payload = blocks[offset + 2]
            for token in yaml.scan(payload, Loader=_UnityLoader):
                if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                    raise UnityDocumentError('显式文档不支持 YAML 链接或自定义标签。')
            value = yaml.load(payload, Loader=_UnityLoader)
            asset = value.get('MonoBehaviour') if isinstance(value, dict) else None
            if (not isinstance(asset, dict) or asset.get('m_Script', {}).get('guid') != DOCUMENT_SCRIPT_GUID
                    or asset.get('m_EditorClassIdentifier') != 'Unity.RandomRealm.Gameplay.Builds::Unity.RandomRealm.Gameplay.DevsRealmDocumentAsset'):
                raise UnityDocumentError('显式来源不是预期的 DevsRealm 文档类型。')
            matches.append(asset)
    except (UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise UnityDocumentError('显式文档来源格式无效。') from exc
    if len(matches) != 1:
        raise UnityDocumentError('显式文档 local fileID 未找到或重复。')
    document = _document(matches[0], relative, guid, revision, meta_revision)
    document['localFileId'] = local_file_id
    return resolve_document_media(root, document, image_bindings, _known_texture_identities([document])) if resolve_media else document


def read_owned_display_documents(root, *, resolve_media=True):
    """Bounded top-level owned Device bundles; never inspect scenes or Library."""
    relative_root = 'Assets/GameData/Builds/DeviceEditor'
    try:
        directory = _path(root, relative_root)
    except FileNotFoundError:
        return []
    documents, seen, count = [], set(), 0
    with os.scandir(directory) as entries:
        names = []
        for entry in entries:
            count += 1
            if count > MAX_SOURCE_ENTRIES:
                raise UnityDocumentError('设备私有文档目录超过读取限制。')
            if re.fullmatch(r'Device-[0-9a-f]{32}\.asset', entry.name):
                names.append(entry.name)
    for name in sorted(names):
        relative = relative_root + '/' + name
        guid, meta_revision = _meta(root, relative + '.meta')
        meta_raw = _read(root, relative + '.meta', MAX_META_BYTES)[0]
        try:
            metadata = yaml.load(meta_raw.decode('utf-8-sig'), Loader=_UnityLoader)
            ownership = json.loads(metadata['NativeFormatImporter']['userData'], object_pairs_hook=_unique_json)
        except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError, RecursionError) as exc:
            raise UnityDocumentError('设备私有文档 ownership 无效。') from exc
        owner_id = name[7:-6]
        if (not isinstance(ownership, dict) or ownership.get('schema') != 'random-realm-device-editor-v1'
                or ownership.get('ownerId') != owner_id or ownership.get('bundleGuid') != guid
                or not isinstance(ownership.get('rootKey'), str)
                or not ownership['rootKey'].startswith(('scene:GlobalObjectId_', 'prefab:'))):
            raise UnityDocumentError('设备私有文档 ownership 与来源不一致。')
        raw, revision = _read(root, relative, MAX_ASSET_BYTES)
        try:
            text = raw.decode('utf-8-sig')
            blocks = re.split(r'^--- !u!(\d+) &(\d+)\r?\n', text, flags=re.M)
            parents = []
            for offset in range(1, len(blocks), 3):
                if blocks[offset] == '114' and int(blocks[offset + 1]) == 11400000:
                    payload = blocks[offset + 2]
                    for token in yaml.scan(payload, Loader=_UnityLoader):
                        if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                            raise UnityDocumentError('设备父资产不支持 YAML 链接或标签。')
                    parents.append(yaml.load(payload, Loader=_UnityLoader).get('MonoBehaviour'))
        except (UnicodeError, yaml.YAMLError, AttributeError, RecursionError) as exc:
            raise UnityDocumentError('设备私有文档父资产格式无效。') from exc
        if (len(parents) != 1 or not isinstance(parents[0], dict)
                or parents[0].get('m_EditorClassIdentifier') != 'Unity.RandomRealm.Gameplay.Builds::Unity.RandomRealm.Gameplay.InteractiveDisplayContent'
                or parents[0].get('m_Script', {}).get('guid') != '16ac4c2bcf3828841b5285ee4875a0eb'):
            raise UnityDocumentError('设备父资产不是预期的 InteractiveDisplayContent。')
        tabs = parents[0].get('m_Tabs')
        if not isinstance(tabs, list) or len(tabs) > MAX_DOCUMENTS:
            raise UnityDocumentError('设备标签清单无效。')
        for index, tab in enumerate(tabs):
            reference = tab.get('m_Document') if isinstance(tab, dict) else None
            if not isinstance(reference, dict) or set(reference) != {'fileID'}:
                raise UnityDocumentError('设备私有标签必须引用本bundle子文档。')
            file_id = _integer(reference['fileID'], '设备文档 local fileID', minimum=1)
            key = (guid, file_id)
            if key in seen:
                raise UnityDocumentError('设备标签包含重复文档绑定。')
            seen.add(key)
            document = read_bound_document(root, relative, guid, file_id, resolve_media=resolve_media)
            if not document['id'].startswith('device-editor-' + owner_id + '-'):
                raise UnityDocumentError('设备私有文档内容身份与owner不一致。')
            document.update(scope='displayContent', displayOwnerId=owner_id, displayTabIndex=index,
                            displayLabel=_text(tab.get('m_Label'), '设备标签', maximum=4096),
                            categoryTitle='设备私有展示', categoryOrder=-1,
                            expectedLibrary={'kind': 'displayContent', 'path': relative, 'guid': guid,
                                             'revision': revision, 'metaRevision': meta_revision})
            documents.append(document)
        if _read(root, relative, MAX_ASSET_BYTES)[1] != revision or _read(root, relative + '.meta', MAX_META_BYTES)[1] != meta_revision:
            raise UnitySourceConflict('设备私有文档读取期间发生变化。')
    return documents


def read_explicit_inventory(workspace, bindings):
    """Read only explicitly pinned document/parent pairs (including QA assets).

    This is an injection point for a selected source, not a project-wide scan.
    The parent must be the expected typed asset and reference that exact document.
    """
    root = _workspace(workspace)
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= MAX_DOCUMENTS:
        raise UnityDocumentError('显式来源绑定清单无效。')
    global_guid, global_meta = _meta(root, LIBRARY_PATH + '.meta')
    _, global_revision = _asset(root, LIBRARY_PATH, 'DevsRealmDocumentLibraryAsset', LIBRARY_SCRIPT_GUID)
    identity_root = os.path.normcase(str(root)).rstrip('\\/')
    project_id = _hash(('unity-dev-room-v1\n' + identity_root + '\n' + global_guid).encode('utf-8'))
    documents, seen = [], set()
    for binding in bindings:
        if not isinstance(binding, dict) or not {'path', 'guid', 'localFileId', 'expectedLibrary'} <= set(binding):
            raise UnityDocumentError('显式文档来源绑定字段无效。')
        parent = binding['expectedLibrary']
        if (not isinstance(parent, dict) or set(parent) != {'kind', 'path', 'guid', 'revision', 'metaRevision'}
                or parent['kind'] not in {'devRoomLibrary', 'displayContent'}):
            raise UnityDocumentError('显式文档父来源无效。')
        actual_guid, actual_meta = _meta(root, parent['path'] + '.meta')
        raw, revision = _read(root, parent['path'], MAX_ASSET_BYTES)
        if actual_guid != parent['guid']:
            raise UnitySourceConflict('显式父来源身份已经改变。')
        # A binding fixes identity, not yesterday's version. Read current pins so
        # preview/status can expose edits; push freezes and rechecks those pins.
        observed_parent = {**parent, 'revision': revision, 'metaRevision': actual_meta}
        if parent['kind'] == 'devRoomLibrary':
            asset, _ = _asset(root, parent['path'], 'DevsRealmDocumentLibraryAsset', LIBRARY_SCRIPT_GUID)
            membership = any(isinstance(r, dict) and r.get('guid') == binding['guid']
                             and r.get('fileID') == binding['localFileId'] for r in asset.get('m_Documents', []))
        else:
            try:
                blocks = re.split(r'^--- !u!(\d+) &(\d+)\r?\n', raw.decode('utf-8-sig'), flags=re.M)
                parents = []
                for offset in range(1, len(blocks), 3):
                    if blocks[offset] == '114' and int(blocks[offset + 1]) == 11400000:
                        payload = blocks[offset + 2]
                        for token in yaml.scan(payload, Loader=_UnityLoader):
                            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                                raise UnityDocumentError('显式父来源不支持 YAML 链接或标签。')
                        parents.append(yaml.load(payload, Loader=_UnityLoader).get('MonoBehaviour'))
            except (UnicodeError, yaml.YAMLError, AttributeError, RecursionError) as exc:
                raise UnityDocumentError('显式父来源格式无效。') from exc
            if (len(parents) != 1 or parents[0].get('m_EditorClassIdentifier') !=
                    'Unity.RandomRealm.Gameplay.Builds::Unity.RandomRealm.Gameplay.InteractiveDisplayContent'):
                raise UnityDocumentError('显式父来源不是 InteractiveDisplayContent。')
            membership = (binding['path'] == parent['path'] and binding['guid'] == parent['guid']
                          and any(isinstance(t, dict) and t.get('m_Document') == {'fileID': binding['localFileId']}
                                  for t in parents[0].get('m_Tabs', [])))
        if not membership:
            raise UnityDocumentError('显式文档不属于所选父来源。')
        key = (binding['guid'], binding['localFileId'])
        if key in seen:
            raise UnityDocumentError('显式来源包含重复文档绑定。')
        seen.add(key)
        hints = binding.get('images', {})
        if not isinstance(hints, dict) or any(not _GUID.fullmatch(str(k)) for k in hints):
            raise UnityDocumentError('显式图片绑定清单无效。')
        document = read_bound_document(root, binding['path'], binding['guid'], binding['localFileId'], hints, resolve_media=False)
        document['_explicitImageBindings'] = hints
        for field in ('id',):
            if field in binding and binding[field] != document[field]:
                raise UnitySourceConflict('显式文档身份或版本已经改变。')
        document.update(scope='displayContent' if parent['kind'] == 'displayContent' else 'explicitLibrary',
                        expectedLibrary=observed_parent)
        documents.append(document)
    known_identities = _known_texture_identities(documents)
    for document in documents:
        hints = document.pop('_explicitImageBindings')
        resolve_document_media(root, document, hints, known_identities)
    categories = [{'id': value, 'order': value, 'title': '显式内容 ' + str(value), 'summary': '明确选定的游戏内容来源。'}
                  for value in sorted({d['category'] for d in documents})]
    return {'workspace': str(root), 'identityRoot': identity_root, 'projectId': project_id,
            'revision': _hash(json.dumps(documents, ensure_ascii=False, sort_keys=True).encode('utf-8')),
            'library': {'kind': 'devRoomLibrary', 'path': LIBRARY_PATH, 'guid': global_guid,
                        'revision': global_revision, 'metaRevision': global_meta},
            'categories': categories, 'documents': documents}
