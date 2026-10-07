"""Shared workflow routes; host handlers enforce desktop or paired-phone access."""
from urllib.parse import parse_qs
import json
from workflow_service import WorkflowError


def send_workflow_events(handler, service, query, *, authorize=None):
    """One authenticated result subscription; no dispatch or queue polling."""
    if handler.command != "GET":
        raise WorkflowError("讨论事件只支持 GET。", 405)
    operation = getattr(service, "mobile_dialogue_subscribe", None)
    if not callable(operation):
        raise WorkflowError("电脑端讨论事件组件尚未更新。", 503)
    slots = handler.server._workflow_event_slots
    if not slots.acquire(blocking=False):
        raise WorkflowError("讨论连接已满，请关闭其它讨论页后重试。", 429)
    stream, started = None, False
    try:
        stream = operation(query, authorize=authorize)
        if authorize:
            authorize()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Referrer-Policy", "same-origin")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Connection", "close")
        handler.end_headers()
        started = True
        handler.close_connection = True
        while not service._stop.is_set():
            frame = stream.next_event(timeout=25)
            if authorize:
                authorize()
            # Comments keep only the transport alive; no periodic result read.
            payload = ("event: " + frame["event"] + "\ndata: " + json.dumps(frame["data"],
                ensure_ascii=False, separators=(",", ":")) + "\n\n") if frame else ": keepalive\n\n"
            handler.wfile.write(payload.encode("utf-8"))
            handler.wfile.flush()
    except Exception:
        # After headers, expiration, a changed session or a disconnected socket
        # ends this response. Never append a second JSON response to the stream.
        if not started:
            raise
    finally:
        if stream is not None:
            stream.close()
        slots.release()


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


def workflow_get(service, action, query, *, prefix="/api/workflow", desktop=False, authorize=None):
    if service is None:
        raise WorkflowError("电脑端工作组件尚未更新。", 503)
    guide = {"mobile/dialogue/guide-source": "mobile_dialogue_guide_source_get",
             "mobile/dialogue/guide-reply": "mobile_dialogue_guide_reply_get",
             "mobile/dialogue/guide-inbox": "mobile_dialogue_guide_inbox"}
    if action in guide:
        return getattr(service, guide[action])(query, prefix=prefix, desktop=desktop, authorize=authorize)
    if action == "mobile/dialogue/guide-send-receipt":
        return service.mobile_dialogue_guide_send_receipt(query, prefix=prefix, authorize=authorize)
    if action == "mobile/dialogue/send-receipt":
        return service.mobile_dialogue_send_receipt(query, prefix=prefix, authorize=authorize)
    if action == "codex-work/config":
        if query:
            raise WorkflowError("Work 配置地址无效。")
        if authorize:
            authorize()
        return service.codex_work_config()
    if action == "codex-work/runs":
        return service.codex_work_runs(query, prefix=prefix, authorize=authorize)
    if action == "subscription/status":
        if query:
            raise WorkflowError("订阅连接请求地址无效。")
        subscription = getattr(service, "subscription", None)
        return subscription.get_status() if subscription else {
            "connected": False, "connectionId": None, "catalogRevision": None,
            "models": [], "status": "请在电脑连接 ChatGPT 订阅。", "busy": False, "error": None}
    if action == "app-work-review":
        operation = getattr(service, "app_work_review", None)
        if not callable(operation):
            raise WorkflowError("电脑端工作组件尚未更新。", 503)
        return operation(query, prefix=prefix, authorize=authorize)
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
    guide = {"mobile/dialogue/guide-source": "mobile_dialogue_guide_source",
             "mobile/dialogue/guide-reply": "mobile_dialogue_guide_reply"}
    if action in guide:
        return getattr(service, guide[action])(body, prefix=prefix, desktop=desktop, authorize=authorize)
    if action in {"codex-work/setup", "codex-work/workspaces"} and not desktop:
        raise WorkflowError("请在电脑明确配置 Work 沙箱与工作区权限。", 403, "codex_work_desktop_required")
    if action.startswith("subscription/"):
        if not desktop:
            raise WorkflowError("请在电脑完成订阅连接设置。", 403)
        if not isinstance(body, dict) or body:
            raise WorkflowError("请从订阅连接页面明确操作。")
        if authorize:
            authorize()
        subscription = getattr(service, "subscription", None)
        if subscription is None:
            raise WorkflowError("订阅连接组件尚未更新。", 503)
        operations = {"subscription/signin": "begin_signin", "subscription/models": "refresh_catalog",
                      "subscription/disconnect": "disconnect"}
        operation = operations.get(action)
        if operation is None:
            raise WorkflowError("订阅接口不存在。", 404)
        result = getattr(subscription, operation)()
        if authorize:
            authorize()
        return result
    operations = {"create": "create", "message": "add_message",
                  "submit": "submit", "discuss": "discuss",
                  "transcribe": "transcribe", "retry": "retry",
                  "task-record": "task_record", "app-work": "app_work", "app-work/end": "end_app_work",
                  "incubator/create": "incubator_create", "incubator/update": "incubator_update",
                  "incubator/publish": "incubator_publish",
                  "incubator/refinement/pause": "incubator_refinement_pause",
                  "conversations/request": "conversations_request"}
    operations.update({"codex-work/review": "codex_work_review", "codex-work/submit": "codex_work_submit",
                       "codex-work/cancel": "codex_work_cancel"})
    operations.update({"mobile/dialogue/open": "mobile_dialogue_open", "mobile/dialogue/draft": "mobile_dialogue_draft",
        "mobile/dialogue/clear": "mobile_dialogue_clear", "mobile/dialogue/send": "mobile_dialogue_send",
        "mobile/dialogue/cancel-pending": "mobile_dialogue_cancel_pending",
        "mobile/dialogue/guide-send": "mobile_dialogue_guide_send",
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
        if action == "codex-work/setup":
            return service.codex_work_setup(body, authorize=authorize)
        if action == "codex-work/workspaces":
            return service.configure_codex_work(body, authorize=authorize)
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
