"""Desktop-only Dev Room content and receipt routes.

The hosting handler owns Host/Origin authorization. This adapter deliberately
does not expose project paths, images or mutation routes to the paired phone.
"""
from urllib.parse import parse_qs


GET_FIELDS = {
    'state': {'expectedRoot', 'id', 'language'},
    'sync/status': {'expectedRoot', 'language'},
    'sync/preview': {'expectedRoot', 'language'},
    'sync/receipt': {'expectedRoot', 'requestId', 'language'},
    'media': {'expectedRoot', 'id', 'section', 'revision', 'language'},
    'media/draft': {'expectedRoot', 'id', 'section', 'revision', 'language', 'stagingName'},
}


def _query(action, query):
    values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
    if (action not in GET_FIELDS or set(values) - GET_FIELDS[action]
            or not values.get('expectedRoot') or any(len(item) != 1 for item in values.values())):
        raise ValueError('Dev Room 请求地址无效。')
    return {key: item[0] for key, item in values.items()}


def dev_room_get(service, sync, action, query):
    values = _query(action, query)
    root = values['expectedRoot']
    language = values.get('language')
    if action == 'state':
        return sync.document_state(root, values.get('id', 'overview'), language=language)
    if action == 'sync/status':
        return sync.status(root, language=language)
    if action == 'sync/preview':
        return sync.preview(root, language=language)
    if action == 'sync/receipt':
        if not values.get('requestId'):
            raise ValueError('同步回执请求缺少标识。')
        return sync.receipt(root, values['requestId'])
    if not all(values.get(key) for key in ('id', 'section', 'revision')):
        # Zero is the first section and is a non-empty query string.
        raise ValueError('图片请求缺少文档、章节或版本。')
    try:
        section = int(values['section'])
    except ValueError as exc:
        raise ValueError('图片章节无效。') from exc
    if str(section) != values['section'] or section < 0:
        raise ValueError('图片章节无效。')
    if action == 'media/draft':
        if not values.get('stagingName'):
            raise ValueError('图片草稿请求缺少上传标识。')
        return sync.draft_media(root, values['id'], section, values['revision'],
                                values['stagingName'], language=language)
    return sync.media(root, values['id'], section, values['revision'], language=language)


def dev_room_post(service, sync, action, payload):
    if action == 'save':
        return sync.save_document(payload)
    if action == 'sync/import':
        return sync.import_documents(payload)
    if action == 'sync/push':
        return sync.push_intent(payload)
    if action == 'media/upload':
        return sync.upload_media(payload)
    raise ValueError('Dev Room 保存地址无效。')
