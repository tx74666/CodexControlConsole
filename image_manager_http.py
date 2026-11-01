"""Desktop-only Image manager dispatch; the HTTP host enforces local origin."""
from urllib.parse import parse_qs


def image_get(service, action, query, notion=None):
    values = parse_qs(query, keep_blank_values=True)
    if any(len(value) != 1 for value in values.values()):
        raise ValueError('图片查询参数不可重复。')
    values = {key: value[0] for key, value in values.items()}
    if action == 'state' and not values:
        return {**service.state(), **(notion.state() if notion is not None else {})}
    if action == 'operation' and not set(values) - {'requestId'} and notion is not None:
        return notion.operation(values.get('requestId'))
    if action == 'preview' and not set(values) - {'path', 'expectedRoot', 'space'}:
        if not values.get('expectedRoot'):
            raise ValueError('请先选择图片文件夹。')
        return service.image(values.get('path'), values['expectedRoot'], space=values.get('space', 'root'))
    raise ValueError('图片读取地址无效。')


def image_post(service, action, payload, notion=None):
    if not isinstance(payload, dict):
        raise ValueError('图片请求内容必须是对象。')
    if action == 'config':
        if notion is not None and notion.busy:
            raise ValueError('图片正在同步，请等本次结果返回后再更换位置。')
        if set(payload) - {'root', 'deviceRoot', 'notionPage', 'expectedRoot'}:
            raise ValueError('图片文件夹设置无效。')
        return {**service.configure(payload), **(notion.state() if notion is not None else {})}
    if not isinstance(payload.get('expectedRoot'), str) or not payload['expectedRoot']:
        raise ValueError('图片文件夹身份缺失，请重新读取。')
    if action in {'apply', 'restore', 'metadata', 'naming-apply', 'naming-restore'} and notion is not None and notion.busy:
        raise ValueError('图片正在同步，请等本次结果返回后再修改本地图片或方案。')
    if action == 'scan' and not set(payload) - {'expectedRoot'}:
        return service.scan(payload)
    if action == 'apply' and not set(payload) - {'expectedRoot', 'planId', 'decisions'}:
        return service.apply(payload)
    if action == 'restore' and not set(payload) - {'expectedRoot', 'planId'}:
        return service.restore(payload)
    if action == 'metadata' and not set(payload) - {'expectedRoot', 'path', 'sha256', 'space', 'groupTitle', 'variantLabel', 'derivedFromId'}:
        return service.annotate(payload)
    if action == 'naming-plan' and not set(payload) - {'expectedRoot', 'entries'}:
        return service.naming_plan(payload)
    if action == 'naming-apply' and not set(payload) - {'expectedRoot', 'planId'}:
        return service.naming_apply(payload)
    if action == 'naming-restore' and not set(payload) - {'expectedRoot', 'planId'}:
        return service.naming_restore(payload)
    if action == 'sync' and not set(payload) - {'expectedRoot', 'source', 'target', 'requestId'}:
        source, target = payload.get('source'), payload.get('target')
        if source not in {'local', 'console', 'device', 'notion'} or target not in {'console', 'local', 'device', 'notion', 'all'}:
            raise ValueError('请选择同步来源和目标。')
        if source == 'notion' or target in {'notion', 'all'}:
            if notion is None:
                raise ValueError('Notion 同步连接尚未就绪；本地图库与导入功能可以正常使用。')
            return notion.sync(payload)
        if source == 'local' and target == 'console':
            return service.scan({'expectedRoot': payload['expectedRoot']})
        if source in {'local', 'console'} and target == 'local':
            return service.scan({'expectedRoot': payload['expectedRoot']})
        if source in {'local', 'console'} and target == 'device':
            if not service.state().get('deviceRoot'):
                return service.scan({'expectedRoot': payload['expectedRoot']})
            return service.sync_device({'expectedRoot': payload['expectedRoot'], 'direction': 'to-device'})
        if source == 'device' and target == 'console':
            return service.sync_device({'expectedRoot': payload['expectedRoot'], 'direction': 'from-device'})
        if source == 'console' and target == 'console':
            return service.scan({'expectedRoot': payload['expectedRoot']})
        raise ValueError('此同步方向不适用。')
    raise ValueError('图片操作地址或参数无效。')
