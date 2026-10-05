"""Approved ordinary Chat Native Messaging host; stdlib, no App/API/database writer.

Registration is deliberately absent. Chrome supplies only the fixed extension
origin. The fixed private approval file must equal the existing store setting.
"""
from __future__ import annotations

import json
from multiprocessing import AuthenticationError
import os
from pathlib import Path
import struct
import sqlite3
import sys
import threading

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_chat_relay import EXTENSION_ID, HOST_NAME, MAX_FRAME, PROTOCOL, decode, encode, fixed_approval


def read_frame(stream):
    header = read_exact(stream, 4, allow_eof=True)
    if header is None:
        return None
    size = struct.unpack("<I", header)[0]
    if not 0 < size <= MAX_FRAME:
        raise ValueError("native_frame_size_invalid")
    data = read_exact(stream, size)
    return decode(data)


def read_exact(stream, size, allow_eof=False):
    parts, remaining = [], size
    while remaining:
        part = stream.read(remaining)
        if not part:
            if allow_eof and remaining == size:
                return None
            raise ValueError("native_frame_truncated")
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)


def write_frame(stream, message):
    data = encode(message)
    stream.write(struct.pack("<I", len(data)) + data)
    stream.flush()


def approved_config(environ=None):
    return fixed_approval(environ=environ)


def forward_product(connection, target, write_lock, stop, exit_process):
    try:
        while not stop.is_set():
            message = decode(connection.recv_bytes(MAX_FRAME))
            with write_lock:
                write_frame(target, message)
    except (EOFError, OSError, ValueError):
        stop.set()
        connection.close()
        # This is the standalone native host's own process, never the Console or
        # another user application. Exit also releases a blocked stdin read.
        exit_process(0)


def main(argv=None, stdin=None, stdout=None, exit_process=None):
    args = list(sys.argv[1:] if argv is None else argv)
    source = stdin or sys.stdin.buffer
    target = stdout or sys.stdout.buffer
    # Chromium may append a window handle switch, never arbitrary data paths.
    allowed_origin = "chrome-extension://" + EXTENSION_ID + "/"
    if not args or args[0] != allowed_origin or any(not item.startswith("--parent-window=") or not item.split("=", 1)[1].isdigit() for item in args[1:]):
        write_frame(target, {"protocol": PROTOCOL, "type": "status", "hostName": HOST_NAME, "enabled": False,
                             "approved": False, "configured": False, "clientReady": False, "message": "native_extension_origin_invalid"})
        return 2
    try:
        config = approved_config()
        if not config:
            raise ValueError("not_approved")
        from multiprocessing.connection import Client
        connection = Client(config["pipeName"], family="AF_PIPE", authkey=bytes.fromhex(config["authKeyHex"]))
    except (ValueError, OSError, KeyError, sqlite3.Error, AuthenticationError):
        write_frame(target, {"protocol": PROTOCOL, "type": "status", "hostName": HOST_NAME, "enabled": False,
                             "approved": False, "configured": False, "clientReady": False, "message": "not_approved_or_product_unavailable"})
        return 3
    stop = threading.Event()
    write_lock = threading.Lock()

    receiver = threading.Thread(target=forward_product, args=(connection, target, write_lock, stop, exit_process or os._exit), name="console-native-product", daemon=True)
    receiver.start()
    try:
        while not stop.is_set():
            message = read_frame(source)
            if message is None:
                break
            connection.send_bytes(encode(message))
    except (ValueError, OSError):
        return 4
    finally:
        stop.set()
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
