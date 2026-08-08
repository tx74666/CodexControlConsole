from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import unicodedata
import uuid
import warnings

from PIL import Image, UnidentifiedImageError


REFERENCE_VIEW_SCHEMA = "blackunity.cdesigner.reference-view-set"
REFERENCE_VIEW_VERSION = 1
REFERENCE_VIEW_DIRECTIONS = ("front", "back", "left", "right", "top", "bottom")
REFERENCE_VIEW_ROOT_PARTS = ("References", "CDesigner")
REFERENCE_VIEW_MANIFEST = "reference-views.json"
REFERENCE_VIEW_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
REFERENCE_VIEW_MAX_PIXELS = 64_000_000
REFERENCE_VIEW_MAX_FILE_BYTES = 64 * 1024 * 1024
REFERENCE_VIEW_PREFIX_STOP_TOKENS = {
    "view",
    "views",
    "image",
    "images",
    "img",
    "reference",
    "references",
    "ref",
}
REFERENCE_VIEW_DIRECTION_ALIASES = {
    "front": {"front", "前", "前方", "前面", "正面", "frontview", "front view"},
    "back": {"back", "后", "后方", "背面", "后面", "backview", "back view", "rear"},
    "left": {"left", "左", "左方", "左面", "左侧", "leftview", "left view"},
    "right": {"right", "右", "右方", "右面", "右侧", "rightview", "right view"},
    "top": {"top", "上", "顶部", "上方", "上面"},
    "bottom": {"bottom", "down", "下", "底部", "下面", "底面"},
}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _is_inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def _set_key(value):
    clean = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", clean):
        raise ValueError("Reference set key is invalid")
    return clean


def _slug(value):
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return (clean or "reference-set")[:48].rstrip("-") or "reference-set"


def _strict_number(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise ValueError(f"{label} is outside the supported range")
    return result


def _strict_bool(value, label):
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be true or false")
    return value


def _input_number(mapping, field, current, minimum, maximum, label):
    value = mapping[field] if field in mapping else current
    return _strict_number(value, minimum, maximum, label)


def _input_bool(mapping, field, current, label):
    value = mapping[field] if field in mapping else current
    return _strict_bool(value, label)


def _strict_center(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Reference origin must contain three numbers")
    return [
        _strict_number(item, -1_000_000.0, 1_000_000.0, "Reference origin")
        for item in value
    ]


def _detected_image_extension(filename, data):
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError("Reference image is empty")
    payload = bytes(data)
    if len(payload) > REFERENCE_VIEW_MAX_FILE_BYTES:
        raise ValueError("Reference image is larger than 64 MB")
    suffix = Path(str(filename or "")).suffix.casefold()
    if suffix not in REFERENCE_VIEW_IMAGE_EXTENSIONS:
        raise ValueError("Reference images must be PNG, JPEG, WebP, BMP, or TIFF")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                width, height = image.size
                image_format = str(image.format or "").upper()
                if width <= 0 or height <= 0 or width * height > REFERENCE_VIEW_MAX_PIXELS:
                    raise ValueError("Reference image dimensions are outside the supported range")
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("Reference image could not be decoded") from error
    detected = {
        "PNG": ".png",
        "JPEG": ".jpg",
        "WEBP": ".webp",
        "BMP": ".bmp",
        "TIFF": ".tif",
    }.get(image_format, "")
    if not detected:
        raise ValueError("Reference image contents are not a supported image")
    if suffix in {".jpeg", ".jpg"} and detected == ".jpg":
        return ".jpg", width, height
    if suffix in {".tif", ".tiff"} and detected == ".tif":
        return ".tif", width, height
    if suffix != detected:
        raise ValueError("Reference image extension does not match its contents")
    return detected, width, height


def _normalize_reference_direction_token(token):
    normalized = unicodedata.normalize("NFKC", str(token or "")).casefold().strip()
    if not normalized:
        return None
    normalized = re.sub(r"[\s._-]+", "", normalized)
    for direction, aliases in REFERENCE_VIEW_DIRECTION_ALIASES.items():
        if normalized in aliases:
            return direction
    return None


def _split_reference_label_parts(filename):
    raw = Path(str(filename or "")).stem
    raw = unicodedata.normalize("NFKC", raw).strip()
    return [part for part in re.split(r"[\s_.,()\[\]{}-]+", raw) if part.strip()]


def _infer_reference_direction_and_prefix(filename, direction_hint=None):
    parts = _split_reference_label_parts(filename)
    if not parts:
        return None, ""

    normalized_parts = [unicodedata.normalize("NFKC", part).casefold().strip() for part in parts]
    for index, part in enumerate(normalized_parts):
        direction = _normalize_reference_direction_token(part)
        if direction:
            prefix_parts = []
            for j, raw_part in enumerate(parts):
                raw_part = str(raw_part or "").strip()
                if not raw_part:
                    continue
                normalized_part = unicodedata.normalize("NFKC", raw_part).casefold().strip()
                if j == index or _normalize_reference_direction_token(normalized_part):
                    continue
                if normalized_part in REFERENCE_VIEW_PREFIX_STOP_TOKENS:
                    continue
                prefix_parts.append(raw_part)
            prefix = " ".join(prefix_parts).strip()
            return direction, prefix

    lower = unicodedata.normalize("NFKC", str(filename or "")).casefold()
    for direction, aliases in REFERENCE_VIEW_DIRECTION_ALIASES.items():
        for alias in aliases:
            if alias and alias in lower:
                return direction, ""
    if direction_hint in REFERENCE_VIEW_DIRECTIONS:
        return direction_hint, ""
    return None, ""


def _sanitize_reference_prefix(prefix):
    clean = unicodedata.normalize("NFKC", str(prefix or "")).strip()
    clean = re.sub(r'[<>:"/\\\\|?*]', " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _reference_filename(direction, prefix, extension):
    normalized_prefix = _sanitize_reference_prefix(prefix)
    if normalized_prefix:
        base = f"{normalized_prefix} {direction}"
    else:
        base = direction
    base = re.sub(r"\s+", " ", base).strip(" ._-")
    extension = str(extension or "").lower()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return f"{base}{extension}"


def _available_reference_target(base_target, used):
    target = Path(base_target)
    if str(target) not in used:
        return target
    for suffix in range(2, 100):
        candidate = target.with_name(f"{target.stem}-{suffix}{target.suffix}")
        if str(candidate) not in used:
            return candidate
    raise ValueError("Unable to generate unique reference image filename")


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(bytes(data))
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class ReferenceViewSetService:
    """Project-local, Blender-independent storage for six-direction reference sets."""

    def __init__(self, project_validator):
        self._project_validator = project_validator
        self._lock = threading.RLock()

    def _project(self, value):
        return Path(self._project_validator(value)).resolve()

    def root(self, project):
        blend = self._project(project)
        project_directory = blend.parent.resolve()
        root = project_directory.joinpath(*REFERENCE_VIEW_ROOT_PARTS).resolve()
        if not _is_inside(root, project_directory):
            raise ValueError("Reference view root resolves outside the Blender project")
        return root

    def _directory(self, project, key):
        root = self.root(project)
        directory = (root / _set_key(key)).resolve()
        if not _is_inside(directory, root):
            raise ValueError("Reference set path is outside the project")
        return directory

    def _manifest_path(self, project, key):
        return self._directory(project, key) / REFERENCE_VIEW_MANIFEST

    def _blank_view(self):
        return {
            "file": None,
            "enabled": False,
            "flipHorizontal": False,
            "flipVertical": False,
            "distanceMeters": None,
            "displaySizeMeters": None,
            "opacity": None,
        }

    def _validate_manifest(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Reference set manifest must be an object")
        if payload.get("schema") != REFERENCE_VIEW_SCHEMA or type(payload.get("version")) is not int or payload.get("version") != REFERENCE_VIEW_VERSION:
            raise ValueError("Reference set manifest has an unsupported schema")
        try:
            set_id = str(uuid.UUID(str(payload.get("setId") or "")))
        except (ValueError, AttributeError) as error:
            raise ValueError("Reference set ID is invalid") from error
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("Reference set name is invalid")
        updated_at = payload.get("updatedAt")
        if not isinstance(updated_at, str):
            raise ValueError("Reference set update time is invalid")
        try:
            parsed_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Reference set update time is invalid") from error
        if parsed_time.tzinfo is None or parsed_time.utcoffset() != timezone.utc.utcoffset(parsed_time):
            raise ValueError("Reference set update time must use UTC")
        if payload.get("units") != "METERS":
            raise ValueError("Reference set units must be METERS")

        placement = payload.get("placement")
        if not isinstance(placement, dict):
            raise ValueError("Reference placement is invalid")
        origin = placement.get("origin")
        if not isinstance(origin, list) or len(origin) != 3:
            raise ValueError("Reference origin is invalid")
        for item in origin:
            _strict_number(item, -1_000_000.0, 1_000_000.0, "Reference origin")
        _strict_number(placement.get("displaySizeMeters"), 0.001, 1_000_000.0, "Display size")
        _strict_number(placement.get("distanceMeters"), 0.0, 1_000_000.0, "Reference distance")
        _strict_number(placement.get("opacity"), 0.0, 1.0, "Reference opacity")
        if not isinstance(placement.get("showInFront"), bool):
            raise ValueError("Reference show-in-front setting is invalid")

        views = payload.get("views")
        if not isinstance(views, dict):
            raise ValueError("Reference views are invalid")
        for direction in REFERENCE_VIEW_DIRECTIONS:
            view = views.get(direction)
            if not isinstance(view, dict):
                raise ValueError(f"{direction} reference view is invalid")
            file = view.get("file")
            if file is not None:
                if not isinstance(file, str) or not file or "\\" in file or ":" in file:
                    raise ValueError(f"{direction} reference path is invalid")
                relative = PurePosixPath(file)
                if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
                    raise ValueError(f"{direction} reference path is invalid")
            if view.get("enabled") is True and file is None:
                raise ValueError(f"{direction} cannot be enabled without an image")
            for flag in ("enabled", "flipHorizontal", "flipVertical"):
                if not isinstance(view.get(flag), bool):
                    raise ValueError(f"{direction} {flag} setting is invalid")
            for field, minimum, maximum in (
                ("distanceMeters", 0.0, 1_000_000.0),
                ("displaySizeMeters", 0.001, 1_000_000.0),
                ("opacity", 0.0, 1.0),
            ):
                value = view.get(field)
                if value is not None:
                    _strict_number(value, minimum, maximum, f"{direction} {field}")
        payload["setId"] = set_id
        return payload

    def _read(self, project, key):
        path = self._manifest_path(project, key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError("Reference set was not found") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Reference set manifest could not be read") from error
        self._validate_manifest(payload)
        return payload

    def _response(self, project, key, payload):
        manifest_path = self._manifest_path(project, key)
        result = json.loads(json.dumps(payload))
        result["key"] = _set_key(key)
        result["directory"] = str(manifest_path.parent)
        result["manifestPath"] = str(manifest_path)
        result["viewCount"] = sum(bool(result["views"][direction].get("file")) for direction in REFERENCE_VIEW_DIRECTIONS)
        return result

    def list(self, project):
        root = self.root(project)
        sets = []
        if root.is_dir():
            for directory in root.iterdir():
                if not directory.is_dir() or directory.is_symlink():
                    continue
                try:
                    key = _set_key(directory.name)
                    payload = self._read(project, key)
                    sets.append(self._response(project, key, payload))
                except (OSError, ValueError):
                    continue
        sets.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
        return {"ok": True, "project": str(self._project(project)), "root": str(root), "sets": sets}

    def get(self, project, key):
        payload = self._read(project, key)
        return {"ok": True, "set": self._response(project, key, payload)}

    def _unique_key(self, project, name, set_id):
        root = self.root(project)
        base = f"{_slug(name)}--{str(set_id)[:8]}"
        key = base
        index = 2
        while (root / key).exists():
            key = f"{base[: max(1, 61 - len(str(index)))]}-{index}"
            index += 1
        return key

    def _rename_key(self, project, current_key, set_id, name):
        root = self.root(project)
        base = f"{_slug(name)}--{str(set_id)[:8]}"
        key = _set_key(base)
        if key == current_key:
            return key
        index = 2
        while (root / key).exists():
            key = f"{base[: max(1, 61 - len(str(index)))]}-{index}"
            index += 1
        return _set_key(key)

    def _new_manifest(self, blend, name):
        now = _utc_now()
        return {
            "schema": REFERENCE_VIEW_SCHEMA,
            "version": REFERENCE_VIEW_VERSION,
            "setId": str(uuid.uuid4()),
            "name": name,
            "createdAt": now,
            "updatedAt": now,
            "units": "METERS",
            "source": {"blendFile": blend.name},
            "placement": {
                "origin": [0.0, 0.0, 0.0],
                "displaySizeMeters": 1.0,
                "distanceMeters": 10.0,
                "opacity": 0.35,
                "showInFront": True,
            },
            "views": {direction: self._blank_view() for direction in REFERENCE_VIEW_DIRECTIONS},
        }

    def _merge_request(self, payload, current, blend, name):
        current = json.loads(json.dumps(current))
        if "placement" in payload and not isinstance(payload.get("placement"), dict):
            raise ValueError("Reference placement must be an object")
        placement_input = payload.get("placement") or {}
        placement_current = current.get("placement") if isinstance(current.get("placement"), dict) else {}
        current["name"] = name
        current["updatedAt"] = _utc_now()
        current["units"] = "METERS"
        source_current = current.get("source") if isinstance(current.get("source"), dict) else {}
        current["source"] = {**source_current, "blendFile": blend.name}
        current["placement"] = {
            **placement_current,
            "origin": _strict_center(placement_input.get("origin", placement_current.get("origin", [0.0, 0.0, 0.0]))),
            "displaySizeMeters": _input_number(
                placement_input, "displaySizeMeters", placement_current.get("displaySizeMeters", 1.0),
                0.001, 1_000_000.0, "Display size",
            ),
            "distanceMeters": _input_number(
                placement_input, "distanceMeters", placement_current.get("distanceMeters", 10.0),
                0.0, 1_000_000.0, "Reference distance",
            ),
            "opacity": _input_number(
                placement_input, "opacity", placement_current.get("opacity", 0.35),
                0.0, 1.0, "Reference opacity",
            ),
            "showInFront": _input_bool(
                placement_input, "showInFront", placement_current.get("showInFront", True), "Show in front",
            ),
        }

        if "views" in payload and not isinstance(payload.get("views"), dict):
            raise ValueError("Reference views must be an object")
        incoming_views = payload.get("views") or {}
        current_views = current.get("views") if isinstance(current.get("views"), dict) else {}
        merged_views = {}
        for direction in REFERENCE_VIEW_DIRECTIONS:
            old_view = {
                **self._blank_view(),
                **(current_views.get(direction) if isinstance(current_views.get(direction), dict) else {}),
            }
            if direction in incoming_views and not isinstance(incoming_views.get(direction), dict):
                raise ValueError(f"{direction} reference view must be an object")
            view_input = incoming_views.get(direction) or {}
            old_view["enabled"] = _input_bool(
                view_input, "enabled", old_view.get("enabled", False), f"{direction} enabled",
            )
            old_view["flipHorizontal"] = _input_bool(
                view_input, "flipHorizontal", old_view.get("flipHorizontal", False), f"{direction} horizontal flip",
            )
            old_view["flipVertical"] = _input_bool(
                view_input, "flipVertical", old_view.get("flipVertical", False), f"{direction} vertical flip",
            )
            for field, minimum, maximum, label in (
                ("distanceMeters", 0.0, 1_000_000.0, "distance"),
                ("displaySizeMeters", 0.001, 1_000_000.0, "display size"),
                ("opacity", 0.0, 1.0, "opacity"),
            ):
                value = view_input.get(field, old_view.get(field))
                old_view[field] = None if value is None else _strict_number(
                    value, minimum, maximum, f"{direction} {label}",
                )
            merged_views[direction] = old_view
        current["views"] = merged_views
        return current

    def _requested_removals(self, payload):
        raw = payload.get("removeDirections", [])
        if not isinstance(raw, list):
            raise ValueError("Reference removals must be a list")
        directions = set()
        for item in raw:
            if not isinstance(item, str):
                raise ValueError("Reference removal direction is invalid")
            direction = item.strip().casefold()
            if direction not in REFERENCE_VIEW_DIRECTIONS:
                raise ValueError("Reference removal direction is invalid")
            if direction in directions:
                raise ValueError("Reference removal direction is duplicated")
            directions.add(direction)
        return directions

    def normalize_names(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Reference set rename payload is invalid")
        project = payload.get("project", "")
        key = _set_key(payload.get("key", ""))
        if not key:
            raise ValueError("Reference set key is required")

        with self._lock:
            manifest = self._read(project, key)
            directory = self._directory(project, key)
            images = (directory / "images").resolve()
            if not _is_inside(images, directory):
                raise ValueError("Reference image path is outside the set")

            prefix_candidates = []
            for direction in REFERENCE_VIEW_DIRECTIONS:
                view = manifest["views"].get(direction)
                if not view or not view.get("file"):
                    continue
                candidate_name = str(view.get("originalName") or "")
                if not candidate_name:
                    candidate_name = str(Path(view["file"]).name)
                _, candidate_prefix = _infer_reference_direction_and_prefix(candidate_name, direction)
                if candidate_prefix:
                    sanitized = _sanitize_reference_prefix(candidate_prefix)
                    if sanitized:
                        prefix_candidates.append(sanitized)

            guessed_prefix = ""
            if prefix_candidates:
                guessed_prefix = max(prefix_candidates, key=prefix_candidates.count)
            if not guessed_prefix:
                guessed_prefix = _sanitize_reference_prefix(
                    _infer_reference_direction_and_prefix(manifest.get("name", ""))[1] or manifest.get("name", "")
                )
            guessed_prefix = guessed_prefix.strip()
            if not guessed_prefix:
                guessed_prefix = self._set_key("reference-view")

            renames = []
            used_paths = {str((directory / str(view.get("file"))).resolve()) for view in manifest["views"].values() if view.get("file")}
            for direction in REFERENCE_VIEW_DIRECTIONS:
                view = manifest["views"].get(direction)
                if not view or not view.get("file"):
                    continue
                old_relative = str(view.get("file") or "")
                if not old_relative:
                    continue
                old_path = (directory / old_relative).resolve()
                if not _is_inside(old_path, images) or not old_path.is_file():
                    continue
                extension = old_path.suffix.lower()
                if extension not in REFERENCE_VIEW_IMAGE_EXTENSIONS:
                    continue
                current_key = str(old_path.resolve())
                if current_key not in used_paths:
                    used_paths.add(current_key)
                baseline_targets = set(used_paths)
                baseline_targets.discard(current_key)
                target = _available_reference_target(
                    images / _reference_filename(direction, guessed_prefix, extension),
                    baseline_targets,
                )
                old_key = str(old_path.resolve())
                new_key = str(target.resolve())
                if old_key == new_key:
                    continue
                renames.append((old_path, target, direction))
                used_paths.add(new_key)
                used_paths.discard(old_key)

            manifest_changed = False
            applied = []
            try:
                for old_path, new_path, direction in renames:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    old_path.rename(new_path)
                    manifest["views"][direction]["file"] = new_path.relative_to(directory).as_posix()
                    manifest["views"][direction]["originalName"] = new_path.name
                    applied.append((old_path, new_path, direction))
                    manifest_changed = True

                if not manifest_changed:
                    return {"ok": True, "set": self._response(project, key, manifest)}

                self._validate_manifest(manifest)
                manifest["updatedAt"] = _utc_now()
                _atomic_json(directory / REFERENCE_VIEW_MANIFEST, manifest)
                return {"ok": True, "set": self._response(project, key, manifest)}
            except Exception:
                for old_path, new_path, _ in reversed(applied):
                    try:
                        if new_path.exists():
                            new_path.rename(old_path)
                    except OSError:
                        pass
                raise

    def upsert(self, payload, uploads=None):
        """Commit metadata, replacements, and removals as one manifest transaction.

        New content-addressed assets are fully decoded and staged before the manifest
        is atomically replaced. If any preparation or commit step fails, every asset
        created by this request is removed and the prior manifest remains authoritative.
        """
        if not isinstance(payload, dict):
            raise ValueError("Reference set payload is invalid")
        project = payload.get("project", "")
        blend = self._project(project)
        raw_name = payload.get("name", "Reference Set")
        if not isinstance(raw_name, str):
            raise ValueError("Reference set name must be text")
        name = raw_name.strip()
        if not name or len(name) > 120:
            raise ValueError("Reference set name must be 1 to 120 characters")

        if uploads is None:
            uploads = {}
        if not isinstance(uploads, dict):
            raise ValueError("Reference image uploads are invalid")

        prepared_uploads = {}
        for raw_direction, file in uploads.items():
            if not isinstance(raw_direction, str):
                raise ValueError("Reference image direction is invalid")
            direction = raw_direction.strip().casefold()
            if direction not in REFERENCE_VIEW_DIRECTIONS or direction in prepared_uploads:
                raise ValueError("Reference image direction is invalid or duplicated")
            if not isinstance(file, dict):
                raise ValueError(f"{direction} reference image is missing")
            filename = str(file.get("filename") or "")
            data = file.get("data")
            extension, width, height = _detected_image_extension(filename, data)
            data = bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            prepared_uploads[direction] = {
                "filename": filename,
                "data": data,
                "extension": extension,
                "width": width,
                "height": height,
                "digest": digest,
            }

        removals = self._requested_removals(payload)
        overlap = removals.intersection(prepared_uploads)
        if overlap:
            raise ValueError(f"A reference view cannot be replaced and removed together: {sorted(overlap)[0]}")

        with self._lock:
            key_value = str(payload.get("key") or "").strip()
            if key_value:
                key = _set_key(key_value)
                current = self._read(project, key)
            else:
                current = self._new_manifest(blend, name)
                key = self._unique_key(project, name, current["setId"])

            previous = json.loads(json.dumps(current))
            current = self._merge_request(payload, current, blend, name)
            directory = self._directory(project, key)
            images = (directory / "images").resolve()
            if not _is_inside(images, directory):
                raise ValueError("Reference image path is outside the set")

            for direction in removals:
                current["views"][direction] = self._blank_view()

            targets = {}
            incoming_views = payload.get("views") or {}
            for direction, prepared in prepared_uploads.items():
                target = images / f"{direction}-{prepared['digest']}{prepared['extension']}"
                relative = target.relative_to(directory).as_posix()
                desired_enabled = True
                if isinstance(incoming_views.get(direction), dict) and "enabled" in incoming_views[direction]:
                    desired_enabled = _strict_bool(incoming_views[direction]["enabled"], f"{direction} enabled")
                current["views"][direction].update({
                    "file": relative,
                    "enabled": desired_enabled,
                    "originalName": Path(prepared["filename"].replace("\\", "/")).name,
                    "bytes": len(prepared["data"]),
                    "sha256": prepared["digest"],
                    "width": prepared["width"],
                    "height": prepared["height"],
                })
                targets[direction] = target

            for view in current["views"].values():
                if not view.get("file"):
                    view["enabled"] = False
            self._validate_manifest(current)

            created_targets = []
            manifest_committed = False
            try:
                for direction, target in targets.items():
                    data = prepared_uploads[direction]["data"]
                    if target.exists():
                        if (
                            target.is_symlink()
                            or not _is_inside(target.resolve(), images)
                            or not target.is_file()
                            or target.read_bytes() != data
                        ):
                            raise ValueError("Reference image content-address collision")
                    else:
                        _atomic_bytes(target, data)
                        created_targets.append(target)
                _atomic_json(directory / REFERENCE_VIEW_MANIFEST, current)
                manifest_committed = True
            finally:
                if not manifest_committed:
                    for target in reversed(created_targets):
                        try:
                            target.unlink(missing_ok=True)
                        except OSError:
                            pass
                    if not key_value:
                        for candidate in (images, directory, self.root(project)):
                            try:
                                candidate.rmdir()
                            except OSError:
                                pass

            referenced = {
                str(view.get("file") or "")
                for view in current["views"].values()
                if view.get("file")
            }
            for view in previous["views"].values():
                relative = str(view.get("file") or "")
                if not relative or relative in referenced:
                    continue
                old_path = (directory / relative).resolve()
                if _is_inside(old_path, images):
                    try:
                        old_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            return {"ok": True, "created": not bool(key_value), "set": self._response(project, key, current)}

    def save(self, payload):
        return self.upsert(payload, {})

    def upload(self, project, key, direction, file):
        direction = str(direction or "").strip().casefold()
        if direction not in REFERENCE_VIEW_DIRECTIONS:
            raise ValueError("Reference view direction is invalid")
        if not isinstance(file, dict):
            raise ValueError("Reference image is missing")
        filename = str(file.get("filename") or "")
        data = file.get("data")
        extension, width, height = _detected_image_extension(filename, data)
        digest = hashlib.sha256(bytes(data)).hexdigest()

        with self._lock:
            payload = self._read(project, key)
            directory = self._directory(project, key)
            images = (directory / "images").resolve()
            if not _is_inside(images, directory):
                raise ValueError("Reference image path is outside the set")
            target = images / f"{direction}-{digest[:12]}{extension}"
            old_relative = str(payload["views"][direction].get("file") or "")
            old_path = (directory / old_relative).resolve() if old_relative else None

            target_existed = target.exists()
            if not target_existed:
                _atomic_bytes(target, data)
            relative = target.relative_to(directory).as_posix()
            payload["views"][direction].update({
                "file": relative,
                "enabled": True,
                "originalName": Path(filename.replace("\\", "/")).name,
                "bytes": len(data),
                "sha256": digest,
                "width": width,
                "height": height,
            })
            payload["updatedAt"] = _utc_now()
            try:
                self._validate_manifest(payload)
                _atomic_json(directory / REFERENCE_VIEW_MANIFEST, payload)
            except Exception:
                if not target_existed:
                    target.unlink(missing_ok=True)
                raise
            if old_path and old_path != target.resolve() and _is_inside(old_path, images):
                try:
                    old_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return {"ok": True, "set": self._response(project, key, payload), "direction": direction}

    def image_path(self, project, key, direction):
        direction = str(direction or "").strip().casefold()
        if direction not in REFERENCE_VIEW_DIRECTIONS:
            raise ValueError("Reference view direction is invalid")
        payload = self._read(project, key)
        relative = str(payload["views"][direction].get("file") or "")
        if not relative:
            raise ValueError("Reference image was not found")
        directory = self._directory(project, key)
        path = (directory / relative).resolve()
        if not _is_inside(path, directory / "images") or not path.is_file():
            raise ValueError("Reference image was not found")
        return path

    def remove_view(self, payload):
        project = payload.get("project", "") if isinstance(payload, dict) else ""
        key = payload.get("key", "") if isinstance(payload, dict) else ""
        direction = str(payload.get("direction") or "").strip().casefold() if isinstance(payload, dict) else ""
        if direction not in REFERENCE_VIEW_DIRECTIONS:
            raise ValueError("Reference view direction is invalid")
        with self._lock:
            manifest = self._read(project, key)
            directory = self._directory(project, key)
            relative = str(manifest["views"][direction].get("file") or "")
            manifest["views"][direction] = self._blank_view()
            manifest["updatedAt"] = _utc_now()
            _atomic_json(directory / REFERENCE_VIEW_MANIFEST, manifest)
            if relative and not any(view.get("file") == relative for view in manifest["views"].values()):
                image = (directory / relative).resolve()
                if _is_inside(image, directory / "images"):
                    try:
                        image.unlink(missing_ok=True)
                    except OSError:
                        pass
            return {"ok": True, "set": self._response(project, key, manifest), "direction": direction}

    def delete(self, payload):
        project = payload.get("project", "") if isinstance(payload, dict) else ""
        key = payload.get("key", "") if isinstance(payload, dict) else ""
        with self._lock:
            manifest = self._read(project, key)
            directory = self._directory(project, key)
            for view in manifest["views"].values():
                relative = str(view.get("file") or "")
                if not relative:
                    continue
                image = (directory / relative).resolve()
                if _is_inside(image, directory / "images"):
                    try:
                        image.unlink(missing_ok=True)
                    except OSError:
                        pass
            (directory / REFERENCE_VIEW_MANIFEST).unlink(missing_ok=True)
            images = directory / "images"
            try:
                images.rmdir()
            except OSError:
                pass
            try:
                directory.rmdir()
            except OSError:
                pass
            root = self.root(project)
            try:
                root.rmdir()
            except OSError:
                pass
            return {
                "ok": True,
                "key": _set_key(key),
                "directoryRemoved": not directory.exists(),
                "preservedUnknownFiles": directory.exists(),
            }

    def rename(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Reference set rename payload is invalid")
        project = payload.get("project", "")
        key = _set_key(payload.get("key", ""))
        raw_name = payload.get("name", "")
        if not isinstance(raw_name, str):
            raise ValueError("Reference set name must be text")
        name = raw_name.strip()
        if not name or len(name) > 120:
            raise ValueError("Reference set name must be 1 to 120 characters")
        with self._lock:
            manifest = self._read(project, key)
            set_id = manifest.get("setId")
            if not set_id:
                raise ValueError("Reference set has no ID")
            old_directory = self._directory(project, key)
            new_key = self._rename_key(project, key, set_id, name)
            directory = old_directory
            if new_key != key:
                root = self.root(project)
                target = (root / new_key).resolve()
                if not _is_inside(target, root):
                    raise ValueError("Reference set path is outside the project")
                old_directory.rename(target)
                directory = target

            manifest["name"] = name
            manifest["updatedAt"] = _utc_now()
            is_valid = False
            try:
                self._validate_manifest(manifest)
                is_valid = True
            finally:
                if not is_valid and new_key != key and directory != old_directory:
                    try:
                        directory.rename(old_directory)
                    except OSError:
                        pass

            _atomic_json(directory / REFERENCE_VIEW_MANIFEST, manifest)
            return {"ok": True, "set": self._response(project, new_key, manifest)}
