import json
import time
from pathlib import Path

import bpy


OUTPUT_PATH = Path(r"D:\Codex\ControlConsole\cache\blender_live_selection.json")
NAMESPACE_KEY = "codex_control_live_selection_writer"


def object_payload(obj):
    if obj is None:
        return {}
    return {
        "name": obj.name,
        "type": getattr(obj, "type", ""),
        "materials": [
            slot.material.name
            for slot in getattr(obj, "material_slots", [])
            if getattr(slot, "material", None)
        ],
    }


def write_live_selection():
    active = getattr(bpy.context.view_layer.objects, "active", None)
    selected = list(getattr(bpy.context, "selected_objects", []))
    payload = {
        "project": bpy.data.filepath,
        "activeObject": object_payload(active),
        "selectedObjects": [object_payload(obj) for obj in selected],
        "updatedTimestamp": time.time(),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0.8


old_writer = bpy.app.driver_namespace.get(NAMESPACE_KEY)
if old_writer and bpy.app.timers.is_registered(old_writer):
    bpy.app.timers.unregister(old_writer)

bpy.app.driver_namespace[NAMESPACE_KEY] = write_live_selection
write_live_selection()
bpy.app.timers.register(write_live_selection, persistent=True)
