"""Shared desktop and authenticated phone resource route dispatch."""
from urllib.parse import parse_qs
from resource_preview import fetch_metadata


def resource_get(service, action, query):
    if action != "state":
        raise ValueError("资源入口没有此功能。")
    values = parse_qs(query, keep_blank_values=True)
    if (set(values) - {"expectedRoot", "q", "kind", "status"}
            or any(len(value) != 1 for value in values.values())):
        raise ValueError("资源查询参数无效。")
    return service.state(**{key: value[0] for key, value in values.items()})


def resource_post(service, action, payload, authorize=None):
    if not isinstance(payload, dict):
        raise ValueError("资源请求内容无效。")
    if authorize:
        authorize()
    if action == "search":
        return service.search(payload, authorize=authorize)
    if action == "save":
        return service.save(payload, authorize=authorize)
    if action == "preview":
        if set(payload) - {"url", "expectedRoot"}:
            raise ValueError("网页预览参数无效。")
        root = payload.get("expectedRoot")
        service.state(expectedRoot=root or "")
        result = fetch_metadata(payload.get("url"))
        if authorize:
            authorize()
        service.state(expectedRoot=root or "")
        return result
    raise ValueError("资源入口没有此功能。")
