import bpy
import json


def image_path(image):
    if image is None:
        return ""
    try:
        return bpy.path.abspath(image.filepath)
    except Exception:
        return image.filepath or ""


rows = []
for material in bpy.data.materials:
    if "OuterWall_Stone" not in material.name and "Outer Wall Stone" not in material.name:
        continue
    if not material.use_nodes or material.node_tree is None:
        continue
    for node in material.node_tree.nodes:
        if node.bl_idname != "ShaderNodeTexImage":
            continue
        image = node.image
        rows.append({
            "material": material.name,
            "node": node.name,
            "label": node.label,
            "image": image.name if image else "",
            "path": image_path(image),
            "colorspace": image.colorspace_settings.name if image else "",
        })

print("__CODEX_JSON_START__" + json.dumps({
    "file": bpy.data.filepath,
    "rows": rows,
}, ensure_ascii=False, indent=2) + "__CODEX_JSON_END__")
