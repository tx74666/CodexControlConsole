"""Shared workflow routes; host handlers enforce desktop or paired-phone access."""
from urllib.parse import parse_qs
from workflow_service import WorkflowError


def workflow_import_idea(service, fields, files, *, prefix="/api/workflow", authorize=None):
    if service is None:
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    operation = getattr(service, "mobile_idea_import", None)
    if not callable(operation):
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    return operation(fields, files, prefix=prefix, authorize=authorize)


def workflow_upload_dialogue(service, fields, files, *, prefix="/api/workflow", authorize=None):
    operation = getattr(service, "mobile_dialogue_upload", None)
    if not callable(operation):
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    return operation(fields, files, prefix=prefix, authorize=authorize)


def workflow_get(service, action, query, *, prefix="/api/workflow"):
    if service is None:
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    mobile = {"mobile/dialogue": "mobile_dialogue_get", "mobile/ideas": "mobile_ideas", "mobile/idea": "mobile_idea"}
    if action in mobile:
        return getattr(service, mobile[action])(query, prefix=prefix)
    if action == "config":
        if query:
            raise WorkflowError("工作配置请求地址无效。")
        return service.config()
    if action == "records":
        return service.list(query, prefix=prefix)
    if action == "incubator":
        return service.incubator_list(query, prefix=prefix)
    if action == "conversations":
        return service.conversations_list(query)
    if action == "conversations/thread":
        values = parse_qs(query, keep_blank_values=True)
        if len(query) > 100 or set(values) != {"id"} or len(values["id"]) != 1:
            raise WorkflowError("会话缓存请求地址无效。")
        return service.conversations_thread(values["id"][0])
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
    operations = {"create": "create", "message": "add_message",
                  "submit": "submit", "discuss": "discuss",
                  "transcribe": "transcribe", "retry": "retry",
                  "task-record": "task_record", "app-work": "app_work", "app-work/end": "end_app_work",
                  "incubator/create": "incubator_create", "incubator/update": "incubator_update",
                  "incubator/publish": "incubator_publish",
                  "incubator/refinement/pause": "incubator_refinement_pause",
                  "conversations/request": "conversations_request"}
    operations.update({"mobile/dialogue/open": "mobile_dialogue_open", "mobile/dialogue/draft": "mobile_dialogue_draft",
        "mobile/dialogue/clear": "mobile_dialogue_clear", "mobile/dialogue/send": "mobile_dialogue_send",
        "mobile/dialogue/save": "mobile_dialogue_save", "mobile/dialogue/remember": "mobile_dialogue_remember",
        "mobile/idea/update": "mobile_idea_update", "mobile/idea/archive": "mobile_idea_archive",
        "mobile/idea/split": "mobile_idea_split", "mobile/idea/merge": "mobile_idea_merge",
        "mobile/idea/import-status": "mobile_idea_import_status"})
    if action in operations:
        operation = getattr(service, operations[action], None)
        if not callable(operation):
            raise WorkflowError("电脑端工作组件尚未更新。", 503)
        return operation(body, prefix=prefix, authorize=authorize)
    if desktop:
        if action == "app-work/bindings":
            operation = getattr(service, "configure_app_work", None)
            if not callable(operation):
                raise WorkflowError("电脑端工作组件尚未更新。", 503)
            return operation(body, authorize=authorize)
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
