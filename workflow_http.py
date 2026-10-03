"""Shared workflow routes; host handlers enforce desktop or paired-phone access."""
from urllib.parse import parse_qs
from workflow_service import WorkflowError


def workflow_get(service, action, query, *, prefix="/api/workflow"):
    if service is None:
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    if action == "config":
        if query:
            raise WorkflowError("工作配置请求地址无效。")
        return service.config()
    if action == "records":
        return service.list(query, prefix=prefix)
    if action == "incubator":
        return service.incubator_list(query, prefix=prefix)
    if action == "incubator/targets":
        return service.incubator_targets(query)
    if action == "incubator/dispatches":
        if query:
            raise WorkflowError("发布列表请求地址无效。")
        return service.incubator_dispatches()
    if action == "record":
        values = parse_qs(query, keep_blank_values=True)
        if len(query) > 100 or set(values) != {"id"} or len(values["id"]) != 1:
            raise WorkflowError("工作记录请求地址无效。")
        return service.detail(values["id"][0], prefix=prefix)
    raise WorkflowError("工作接口不存在。", 404)


def workflow_post(service, action, body, *, prefix="/api/workflow", desktop=False, authorize=None):
    if service is None:
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    operations = {"create": service.create, "message": service.add_message,
                  "submit": service.submit, "discuss": service.discuss,
                  "transcribe": service.transcribe, "retry": service.retry,
                  "incubator/create": service.incubator_create, "incubator/update": service.incubator_update,
                  "incubator/publish": service.incubator_publish}
    if action in operations:
        return operations[action](body, prefix=prefix, authorize=authorize)
    if desktop:
        if action == "incubator/targets":
            return service.incubator_set_targets(body, authorize=authorize)
        if action == "models":
            if service.models is None:
                raise WorkflowError("模型适配器不可用。", 503)
            service.models.configure(body)
            return service.config()
        if action == "projects":
            return service.configure_projects(body)
        if action == "background":
            if not isinstance(body, dict) or set(body) != {"enabled"}:
                raise WorkflowError("后台接收设置无效。")
            service.configure_background(body["enabled"])
            return service.config()
    raise WorkflowError("工作接口不存在。", 404)
