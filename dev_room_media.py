"""Bounded image decoding and immutable Dev Room media objects.

Only PNG/JPEG pixels are accepted. Uploaded bytes remain in the selected durable
document library; Unity's Editor is the only writer of actual game assets.
"""
import base64
import binascii
import hashlib
from io import BytesIO
from pathlib import Path
import re

from dev_room import DEV_ROOM_PARTS

MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_MEDIA_REQUEST_BYTES = 14 * 1024 * 1024 + 8192
MAX_PIXELS = 16 * 1024 * 1024
MEDIA_PARTS = (*DEV_ROOM_PARTS, '.media', 'objects')
_NAME = re.compile(r'([0-9a-f]{64})\.(png|jpg)')


def inspect_image(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_MEDIA_BYTES:
        raise ValueError('图片须为不超过 10 MiB 的 PNG 或 JPEG。')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        extension, mime = 'png', 'image/png'
    elif raw.startswith(b'\xff\xd8\xff'):
        extension, mime = 'jpg', 'image/jpeg'
    else:
        raise ValueError('图片只接受实际 PNG 或 JPEG 像素，不能上传 SVG 或其他文件。')
    from PIL import Image
    try:
        with Image.open(BytesIO(raw)) as picture:
            if (picture.format not in {'PNG', 'JPEG'} or picture.width < 1 or picture.height < 1
                    or picture.width > 8192 or picture.height > 8192
                    or picture.width * picture.height > MAX_PIXELS
                    or getattr(picture, 'n_frames', 1) != 1):
                raise ValueError('图片尺寸过大或包含动画。')
            dimensions = (picture.width, picture.height)
            picture.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('图片像素无法解码，请使用有效 PNG 或 JPEG。') from exc
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'extension': extension,
            'mimeType': mime, 'size': len(raw), 'width': dimensions[0], 'height': dimensions[1]}


def decode_upload(payload):
    if not isinstance(payload.get('base64'), str) or len(payload['base64']) > (MAX_MEDIA_BYTES + 2) // 3 * 4:
        raise ValueError('图片上传内容超过限制。')
    try:
        raw = base64.b64decode(payload['base64'], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('图片上传编码无效。') from exc
    metadata = inspect_image(raw)
    if payload.get('mimeType') != metadata['mimeType']:
        raise ValueError('图片实际像素与声明格式不符。')
    filename = payload.get('filename')
    if not isinstance(filename, str) or not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename):
        raise ValueError('图片文件名无效。')
    return raw, metadata


def object_name(value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError('图片对象身份无效。')
    return value


def store_object(service, root, raw):
    metadata = inspect_image(raw)
    name = metadata['sha256'] + '.' + metadata['extension']
    service._mkdir(root, *MEDIA_PARTS)
    path = service._checked_path(root, *MEDIA_PARTS, name)
    if path.exists():
        read_object(service, root, name)
    else:
        # Exclusive create makes objects immutable even between Console processes.
        try:
            with path.open('xb') as destination:
                destination.write(raw)
                destination.flush()
                import os
                os.fsync(destination.fileno())
        except FileExistsError:
            read_object(service, root, name)
    service._check_current_root(root)
    return {**metadata, 'stagingName': name}


def read_object(service, root, name):
    name = object_name(name)
    path = service._checked_path(root, *MEDIA_PARTS, name)
    if not path.is_file():
        raise ValueError('已保存的图片对象缺失，请保留文档并重新上传。')
    with path.open('rb') as source:
        raw = source.read(MAX_MEDIA_BYTES + 1)
    metadata = inspect_image(raw)
    if metadata['sha256'] != name.split('.')[0] or metadata['extension'] != name.split('.')[1]:
        raise ValueError('已保存的图片对象校验失败，不能同步。')
    return path, metadata, raw
