"""Only the confirmed record's frozen image bytes cross the native relay.

Frames remain below Chromium's 1 MiB native-host limit. No directory scan,
URL download, mutable filename lookup, or image path reaches the extension.
"""
import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
import re

IMAGE_CHUNK_BYTES = 128 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_TOTAL = 24 * 1024 * 1024
IMAGE_SUFFIXES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def validate_image_contract(value, surface):
    fields = {"version", "verified", "surface", "capturedAt", "source", "observationSha256", "selectors"}
    if (not isinstance(value, dict) or set(value) != fields or value["version"] != 1
            or value["verified"] is not True or value["source"] != "cua" or value["surface"] != surface
            or surface not in {"chrome", "edge"} or not isinstance(value["capturedAt"], str)
            or len(value["capturedAt"]) > 64 or not isinstance(value["observationSha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["observationSha256"])
            or not isinstance(value["selectors"], dict) or set(value["selectors"]) != {"input", "ready", "pending", "source"}
            or any(not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in value["selectors"].values())):
        raise ValueError("relay_image_dom_contract_unverified")
    try:
        if datetime.fromisoformat(value["capturedAt"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("relay_image_dom_contract_unverified")
    except (ValueError, TypeError) as error:
        raise ValueError("relay_image_dom_contract_unverified") from error
    return value


def read_image_contract(surface):
    # Fixed package resources only; no approval/configuration/database mutation.
    directory = Path(__file__).resolve().parent / "extensions"
    paths = [directory / "image-dom-contract.json", directory / "console-chat-relay" / "image-dom-contract.json"]
    for path in paths:
        if path.is_file():
            try:
                if path.stat().st_size > 65536:
                    return None
                return validate_image_contract(json.loads(path.read_text(encoding="utf-8")), surface)
            except (OSError, ValueError, TypeError):
                return None
    return None


def frozen_images(service, db, payload, snapshot, record_id):
    """Read a bounded immutable copy after verifying both original and view bytes."""
    images = payload.get("appFrozen", {}).get("images")
    if not isinstance(images, list) or len(images) > 4:
        raise ValueError("relay_images_invalid")
    ids = [item.get("id") for item in images if isinstance(item, dict)]
    if (len(ids) != len(images) or any(not isinstance(identifier, str) for identifier in ids) or len(set(ids)) != len(ids)
            or ids != payload.get("context", {}).get("attachmentIds") or ids != snapshot.get("attachmentIds")):
        raise ValueError("relay_images_source_mismatch")
    result, total = [], 0
    for item in images:
        identifier, mime = item["id"], item.get("mimeType")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier) or mime not in IMAGE_SUFFIXES:
            raise ValueError("relay_image_type_invalid")
        row = db.execute("SELECT * FROM attachments WHERE id=? AND record_id=?", (identifier, record_id)).fetchone()
        if row is None or row["filename"] != item.get("originalFilename") or row["mime_type"] != item.get("originalMimeType"):
            raise ValueError("relay_images_source_mismatch")
        original = service.attachments_dir / row["filename"]
        path = Path(item.get("path", ""))
        directory = service.attachments_dir.resolve()
        if (original.resolve().parent != directory or path.resolve().parent != directory
                or path.name not in {row["filename"], identifier + ".preview.jpg"}
                or str(path) != str(path.resolve()) or not original.is_file() or not path.is_file()
                or type(item.get("size")) is not int or not 0 < item["size"] <= MAX_IMAGE_BYTES
                or original.stat().st_size != item.get("originalSize")
                or service._file_digest(original) != item.get("originalSha256")):
            raise ValueError("relay_image_changed")
        # Bounded read also detects growth without allocating an unbounded file.
        with path.open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item.get("sha256"):
            raise ValueError("relay_image_changed")
        total += len(data)
        if total > MAX_IMAGE_TOTAL:
            raise ValueError("relay_images_too_large")
        descriptor = {"id": identifier, "name": "console-" + identifier + IMAGE_SUFFIXES[mime],
                      "mimeType": mime, "size": len(data), "sha256": item["sha256"]}
        result.append((descriptor, data))
    return result


def image_frames(protocol, identity, images):
    for descriptor, data in images:
        count = (len(data) + IMAGE_CHUNK_BYTES - 1) // IMAGE_CHUNK_BYTES
        for index in range(count):
            chunk = data[index * IMAGE_CHUNK_BYTES:(index + 1) * IMAGE_CHUNK_BYTES]
            yield {"protocol": protocol, "type": "imageChunk", "dispatchId": identity["dispatchId"],
                   "attemptId": identity["attemptId"], "image": descriptor, "index": index, "count": count,
                   "data": base64.b64encode(chunk).decode("ascii"), "chunkSha256": hashlib.sha256(chunk).hexdigest()}


def image_evidence(value, images, status):
    if (not isinstance(value, dict) or set(value) != {"status", "items"}
            or value["status"] != status or value["items"] != images):
        raise ValueError("relay_image_evidence_mismatch")
