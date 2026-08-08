#!/usr/bin/env python3

import json
import io
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import reference_views as reference_views_module
from reference_views import (
    REFERENCE_VIEW_DIRECTIONS,
    REFERENCE_VIEW_SCHEMA,
    ReferenceViewSetService,
)
from PIL import Image


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_raises(action, message):
    try:
        action()
    except ValueError:
        return
    raise AssertionError(message)


def file_snapshot(directory):
    directory = Path(directory)
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def main():
    with tempfile.TemporaryDirectory(prefix="cdesigner-reference-views-") as temporary:
        project_dir = Path(temporary) / "Any Object"
        project_dir.mkdir()
        blend = project_dir / "asset.blend"
        blend.write_bytes(b"BLENDER")

        def validate_project(value):
            candidate = Path(value).resolve()
            if candidate != blend.resolve():
                raise ValueError("unexpected project")
            return candidate

        service = ReferenceViewSetService(validate_project)
        created = service.save({
            "project": str(blend),
            "name": "Mechanical Part",
            "placement": {
                "origin": [1, 2, 3],
                "displaySizeMeters": 4.5,
                "distanceMeters": 10,
                "opacity": 0.4241226315498352,
                "showInFront": True,
            },
        })
        reference_set = created["set"]
        key = reference_set["key"]
        root = service.root(str(blend))
        renamed_once = service.rename({"project": str(blend), "key": key, "name": "Mechanical Part Front"})
        key = renamed_once["set"]["key"]
        assert_true(
            key == renamed_once["set"]["key"],
            "renamed set key response was not refreshed",
        )
        assert_true(Path(reference_set["directory"]) != Path(renamed_once["set"]["directory"]), "rename should move the folder")
        assert_true(
            not Path(reference_set["directory"]).exists() and Path(renamed_once["set"]["directory"]).exists(),
            "rename should move the reference-view folder and keep destination",
        )
        assert_true(
            renamed_once["set"]["name"] == "Mechanical Part Front",
            "renamed set name was not persisted",
        )
        # collision-safe rename path should auto-append a suffix when target directory exists.
        collision_key = service._rename_key(str(blend), key, renamed_once["set"]["setId"], "Mechanical Part Side")
        collision_directory = root / collision_key
        collision_directory.mkdir(parents=True, exist_ok=True)
        renamed_twice = service.rename({
            "project": str(blend),
            "key": key,
            "name": "Mechanical Part Side",
        })
        key = renamed_twice["set"]["key"]
        assert_true(
            key != collision_key,
            "renamed set should avoid existing target key collisions",
        )
        assert_true(renamed_twice["set"]["name"] == "Mechanical Part Side", "renamed set name was not updated in collision case")
        assert_true(created["created"], "new set was not reported as created")
        set_base, set_suffix = key.split("--", 1)
        assert_true(
            set_base == "mechanical-part-side"
            and len(set_suffix.split("-", 1)[0]) == 8
            and all(char in "0123456789abcdef" for char in set_suffix.split("-", 1)[0]),
            "set folder is not UUID-stable",
        )
        assert_true(reference_set["schema"] == REFERENCE_VIEW_SCHEMA and reference_set["version"] == 1, "manifest schema is wrong")
        assert_true(reference_set["placement"]["origin"] == [1.0, 2.0, 3.0], "generic origin was not saved")
        assert_true(reference_set["placement"]["opacity"] == 0.4241226315498352, "arbitrary manifest precision was rounded")
        assert_true(set(reference_set["views"]) >= set(REFERENCE_VIEW_DIRECTIONS), "six directions are not present")
        assert_true(all(not view["enabled"] and view["file"] is None for view in reference_set["views"].values()), "unconfigured slots must be disabled")
        assert_raises(
            lambda: service.save({
                "project": str(blend),
                "key": key,
                "name": "Mechanical Part",
                "placement": {"opacity": "0.5"},
            }),
            "string numeric settings were silently accepted",
        )
        assert_raises(
            lambda: service.upload(str(blend), key, "front", {"filename": "fake.png", "data": b"\x89PNG\r\n\x1a\nnot-an-image"}),
            "an undecodable image was accepted",
        )

        png_buffer = io.BytesIO()
        Image.new("RGBA", (2, 3), (80, 40, 160, 255)).save(png_buffer, format="PNG")
        png = png_buffer.getvalue()
        original_file_limit = reference_views_module.REFERENCE_VIEW_MAX_FILE_BYTES
        try:
            reference_views_module.REFERENCE_VIEW_MAX_FILE_BYTES = len(png) - 1
            assert_raises(
                lambda: service.upsert(
                    {"project": str(blend), "key": key, "name": "Mechanical Part"},
                    {"front": {"filename": "too-large.png", "data": png}},
                ),
                "the server-side per-image byte limit was not enforced",
            )
        finally:
            reference_views_module.REFERENCE_VIEW_MAX_FILE_BYTES = original_file_limit

        original_pixel_limit = Image.MAX_IMAGE_PIXELS
        try:
            for forced_limit in (4, 2):
                Image.MAX_IMAGE_PIXELS = forced_limit
                assert_raises(
                    lambda: service.upsert(
                        {"project": str(blend), "key": key, "name": "Mechanical Part"},
                        {"front": {"filename": "bomb.png", "data": png}},
                    ),
                    "a Pillow decompression-bomb condition was not normalized to ValueError",
                )
        finally:
            Image.MAX_IMAGE_PIXELS = original_pixel_limit

        uploaded = service.upload(str(blend), key, "front", {"filename": "temporary-attachment.png", "data": png})
        front = uploaded["set"]["views"]["front"]
        assert_true(front["file"].startswith("images/front-") and front["file"].endswith(".png"), "uploaded attachment did not use a stable content-addressed path")
        assert_true(front["enabled"] and front["width"] == 2 and front["height"] == 3, "uploaded view was not configured for Blender")
        assert_true(Path(uploaded["set"]["directory"], *front["file"].split("/")).read_bytes() == png, "stable image copy is missing")
        first_path = Path(uploaded["set"]["directory"], *front["file"].split("/"))

        front_named = service.upload(str(blend), key, "front", {"filename": "shu-left.png", "data": png})
        assert_true(
            front_named["set"]["views"]["front"]["originalName"] == "shu-left.png",
            "originalName was not persisted",
        )
        assert_true(
            Path(front_named["set"]["directory"], *front_named["set"]["views"]["front"]["file"].split("/")).read_bytes() == png,
            "front named image copy is missing",
        )
        service.upload(str(blend), key, "back", {"filename": "shu 后面 view.png", "data": png})
        normalized = service.normalize_names({"project": str(blend), "key": key})["set"]
        front_name = Path(normalized["views"]["front"]["file"]).name
        back_name = Path(normalized["views"]["back"]["file"]).name
        assert_true("shu front" in front_name, "front filename was not normalized")
        assert_true("shu back" in back_name, "back filename was not normalized")
        assert_true(
            (Path(normalized["directory"]) / normalized["views"]["front"]["file"]).exists(),
            "normalized front image should exist",
        )
        assert_true(
            (Path(normalized["directory"]) / normalized["views"]["back"]["file"]).exists(),
            "normalized back image should exist",
        )

        replacement_buffer = io.BytesIO()
        Image.new("RGBA", (3, 2), (20, 120, 60, 255)).save(replacement_buffer, format="PNG")
        replacement_png = replacement_buffer.getvalue()

        set_directory = Path(uploaded["set"]["directory"])
        before_failed_transaction = file_snapshot(set_directory)
        assert_raises(
            lambda: service.upsert(
                {"project": str(blend), "key": key, "name": "Mechanical Part"},
                {
                    "front": {"filename": "replacement.png", "data": replacement_png},
                    "back": {"filename": "broken.png", "data": b"not an image"},
                },
            ),
            "a transaction containing a bad image was accepted",
        )
        assert_true(
            file_snapshot(set_directory) == before_failed_transaction,
            "bad-image transaction changed the old manifest or assets",
        )

        original_atomic_json = reference_views_module._atomic_json
        try:
            def fail_manifest_commit(path, payload):
                raise OSError("injected manifest commit failure")

            reference_views_module._atomic_json = fail_manifest_commit
            try:
                service.upsert(
                    {"project": str(blend), "key": key, "name": "Mechanical Part"},
                    {"front": {"filename": "replacement.png", "data": replacement_png}},
                )
            except OSError:
                pass
            else:
                raise AssertionError("fault-injected transaction unexpectedly succeeded")
        finally:
            reference_views_module._atomic_json = original_atomic_json
        assert_true(
            file_snapshot(set_directory) == before_failed_transaction,
            "fault-injected transaction changed the old manifest or assets",
        )

        png = replacement_png
        uploaded = service.upsert(
            {
                "project": str(blend),
                "key": key,
                "name": "Mechanical Part",
                "views": {"front": {"enabled": True}},
            },
            {"front": {"filename": "replacement.png", "data": png}},
        )
        front = uploaded["set"]["views"]["front"]
        assert_true(not first_path.exists() and front["file"] != first_path.relative_to(uploaded["set"]["directory"]).as_posix(), "replaced image was not committed by content hash")
        manifest = json.loads(Path(uploaded["set"]["manifestPath"]).read_text(encoding="utf-8"))
        assert_true("key" not in manifest, "response-only key leaked into the manifest")
        assert_true(manifest["views"]["front"]["file"] == front["file"], "manifest image path is wrong")
        assert_true(".." not in manifest["views"]["front"]["file"], "manifest image escaped its set")
        manifest["futureTopLevel"] = {"preserve": True}
        manifest["placement"]["futurePlacement"] = "preserve"
        manifest["views"]["front"]["futureView"] = 7
        Path(uploaded["set"]["manifestPath"]).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        saved = service.save({
            "project": str(blend),
            "key": key,
            "name": "Mechanical Part",
            "placement": {
                **manifest["placement"],
                "opacity": 0.6,
            },
            "views": {
                "front": {
                    "enabled": False,
                    "flipHorizontal": True,
                    "flipVertical": True,
                    "distanceMeters": 12,
                    "displaySizeMeters": 5,
                    "opacity": 0.8,
                },
            },
        })["set"]
        front = saved["views"]["front"]
        assert_true(front["file"] == manifest["views"]["front"]["file"], "metadata update swallowed the image")
        assert_true(front["flipVertical"] and front["displaySizeMeters"] == 5.0, "per-view overrides were not saved")
        assert_true(
            saved["futureTopLevel"]["preserve"]
            and saved["placement"]["futurePlacement"] == "preserve"
            and front["futureView"] == 7,
            "unknown future manifest fields were not preserved",
        )
        assert_true(service.image_path(str(blend), key, "front").read_bytes() == png, "image lookup failed")
        assert_true(service.list(str(blend))["sets"][0]["setId"] == saved["setId"], "set persistence failed")

        removed = service.upsert({
            "project": str(blend),
            "key": key,
            "name": "Mechanical Part",
            "removeDirections": ["front"],
        })["set"]
        assert_true(removed["views"]["front"]["file"] is None, "remove view did not clear the manifest")
        assert_true(not (Path(removed["directory"]) / front["file"]).exists(), "remove view left its managed image")

        unknown = Path(removed["directory"]) / "keep-me.txt"
        unknown.write_text("user file", encoding="utf-8")
        deleted = service.delete({"project": str(blend), "key": key})
        assert_true(deleted["preservedUnknownFiles"] and unknown.is_file(), "clear set deleted an unknown user file")
        assert_true(not (unknown.parent / "reference-views.json").exists(), "clear set left the managed manifest")

        print("PASS Reference View Set service")


if __name__ == "__main__":
    main()
