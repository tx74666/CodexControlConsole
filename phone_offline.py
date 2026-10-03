"""Read-only private export for the offline phone app.

The generated packet is intended for the user's local file transfer. It is not
a static-site input and never includes an arbitrary document tree or music.
"""
from datetime import datetime, timezone
import base64
import json
import re

from document_library import MAX_TEXT_BYTES, markdown_image_paths
from workspace_plan import normalize_plan


MAX_EXPORT_BYTES = 8 * 1024 * 1024
FORMAT = "codex-console-phone-data"


def _json_bytes(value):
    # Match the desktop JSON responder, whose separators include spaces. A
    # compact download is smaller, so this also bounds the actual HTTP packet.
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _without_root(value):
    return {key: item for key, item in value.items() if key != "root"}


def _device_payload(value):
    if not isinstance(value, dict):
        return {"status": "unavailable", "currentMemory": {"status": "unavailable"}}
    return {key: value.get(key) for key in ("currentMemory", "model", "cpuModel", "gpuModels",
            "installedMemoryBytes", "sampledAt", "status")}


def build_phone_export(document_library, plan_getter, device_getter, version):
    """Create one bounded packet; all library lookups share the selected root."""
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("手机版本号无效。")
    # This pin also covers a device callback that reads saved snapshot metadata.
    # Even another process changing the settings file cannot redirect nested
    # reads into a second library midway through the export.
    with document_library._document_scope() as root:
        expected_root = str(root)
        plan_result = plan_getter()
        if not isinstance(plan_result, dict):
            raise ValueError("电脑保存的计划清单格式无效。")
        raw_plan = plan_result.get("plan")
        plan = normalize_plan(raw_plan) if raw_plan is not None else None
        error = plan_result.get("error", "")
        if not isinstance(error, str):
            raise ValueError("电脑保存的计划清单状态无效。")
        label = ("电脑已保存的计划与进度。" if plan_result.get("actualDone") is True
                 else "导入电脑保存的计划；电脑浏览器中的勾选进度暂未同步。")
        plan_payload = {"plan": plan, "label": label,
                        "error": error[:600]}
        try:
            device = _device_payload(device_getter())
        except (ValueError, OSError, RuntimeError):
            device = _device_payload(None)
        guide = _without_root(document_library.guide(expectedRoot=expected_root))
        inbox = _without_root(document_library.inbox(expectedRoot=expected_root))
        references = _without_root(document_library.references(expectedRoot=expected_root))
        payload = {"format": FORMAT, "schemaVersion": 1,
                   "exportedAt": datetime.now(timezone.utc).isoformat(),
                   "dashboard": {"version": version, "plan": plan_payload, "device": device,
                                 "documents": {"guide": guide, "inbox": inbox, "references": references}},
                   "files": []}
        used_bytes = len(_json_bytes(payload))
        if used_bytes > MAX_EXPORT_BYTES:
            raise ValueError("离线资料包超过 8 MiB，请减少已登记资料后重试。")
        paths, seen = [], set()
        image_paths, seen_images = [], set()
        for candidate in [item["path"] for item in guide.get("items", [])] + [
                item["path"] for item in inbox.get("entries", [])] + [
                variant["path"] for item in references.get("items", [])
                for variant in item.get("variants", []) if variant.get("available")]:
            if candidate not in seen:
                paths.append(candidate)
                seen.add(candidate)
        for path in paths:
            document = _without_root(document_library.read(path, expectedRoot=expected_root))
            if len(document.get("content", "").encode("utf-8")) > MAX_TEXT_BYTES:
                raise ValueError("单份文件超过 2 MiB，原始文件未更动。")
            used_bytes += len(_json_bytes(document)) + (2 if payload["files"] else 0)
            if used_bytes > MAX_EXPORT_BYTES:
                raise ValueError("离线资料包超过 8 MiB，请减少已登记资料后重试。")
            payload["files"].append(document)
            if document.get('format') == 'markdown':
                try:
                    for image_path in markdown_image_paths(document.get('content', ''), path):
                        identity = image_path.casefold()
                        if identity not in seen_images:
                            image_paths.append(image_path)
                            seen_images.add(identity)
                except ValueError as exc:
                    raise ValueError(f'文檔 {path} 的圖片不能匯出：{exc}') from exc
        if image_paths:
            payload['assets'] = []
            for image_path in image_paths:
                try:
                    image = document_library.image(image_path, expectedRoot=expected_root)
                except (ValueError, OSError) as exc:
                    raise ValueError(f'圖片 {image_path} 不能匯出：{exc}') from exc
                asset = {'path': image_path, 'mimeType': image['mimeType'],
                         'data': base64.b64encode(image['content']).decode('ascii')}
                used_bytes += len(_json_bytes(asset)) + (2 if payload['assets'] else 0)
                if used_bytes > MAX_EXPORT_BYTES:
                    raise ValueError('含圖片的離線資料包超過 8 MiB，請縮小閱讀副本後重試；原始資料未更動。')
                payload['assets'].append(asset)
        # Keep the public size guarantee explicit if the packet structure grows.
        if len(_json_bytes(payload)) > MAX_EXPORT_BYTES:
            raise ValueError("离线资料包超过 8 MiB，原始资料未更动。")
        return payload
