import http.client
import io
import json
from contextlib import contextmanager
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import urllib.parse
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import world_console  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class BoundaryHandler(world_console.ConsoleHandler):
    stream_path = None

    def do_GET(self):
        if urllib.parse.urlparse(self.path).path == "/__stream-test":
            self.send_file_response(
                type(self).stream_path,
                "application/octet-stream",
                filename="stream-test.bin",
            )
            return
        super().do_GET()


@contextmanager
def running_server(
    handler_class=BoundaryHandler,
    *,
    max_request_threads=world_console.MAX_HTTP_REQUEST_THREADS,
    connection_idle_timeout=world_console.HTTP_CONNECTION_IDLE_TIMEOUT_SECONDS,
):
    server = world_console.ConsoleHTTPServer(
        ("127.0.0.1", 0),
        handler_class,
        max_request_threads=max_request_threads,
        connection_idle_timeout=connection_idle_timeout,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        response_headers = {key.casefold(): value for key, value in response.getheaders()}
        return response.status, response_headers, payload
    finally:
        connection.close()


def raw_status(port, header_lines):
    request_bytes = (
        "POST /api/hotkey/start HTTP/1.0\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        + "".join(f"{line}\r\n" for line in header_lines)
        + "\r\n"
    ).encode("ascii")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.sendall(request_bytes)
        client.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    response = b"".join(chunks)
    status_line = response.split(b"\r\n", 1)[0]
    return int(status_line.split()[1]), response


class TrackingReader:
    def __init__(self, source, read_sizes):
        self.source = source
        self.read_sizes = read_sizes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.source.close()

    def fileno(self):
        return self.source.fileno()

    def read(self, size=-1):
        self.read_sizes.append(size)
        return self.source.read(size)


class BoundedBodyReader(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


def multipart_payload(boundary, parts):
    chunks = []
    for headers, data in parts:
        chunks.append(b"--" + boundary + b"\r\n")
        for name, value in headers:
            chunks.append(f"{name}: {value}\r\n".encode("utf-8"))
        chunks.append(b"\r\n")
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(b"--" + boundary + b"--\r\n")
    return b"".join(chunks)


def multipart_handler(body, boundary, *, length=None, content_types=None, content_lengths=None):
    handler = object.__new__(world_console.ConsoleHandler)
    handler.headers = http.client.HTTPMessage()
    for value in content_types or [f'multipart/form-data; boundary="{boundary.decode("ascii")}"']:
        handler.headers.add_header("Content-Type", value)
    length_values = content_lengths if content_lengths is not None else [str(len(body) if length is None else length)]
    for value in length_values:
        handler.headers.add_header("Content-Length", value)
    handler.rfile = BoundedBodyReader(body)
    return handler


def require_no_multipart_temps(directory, message):
    require(not list(Path(directory).glob("codex-console-multipart-*.upload")), message)


def check_multipart_spool_budget(temporary):
    slot_budget = world_console.MultipartSpoolBudget(1, 100, 0)
    first = slot_budget.acquire(60, temporary)
    require(slot_budget.active_count == 1, "multipart upload slot was not reserved")
    require(slot_budget.reserved_bytes == 60, "multipart spool bytes were not reserved")
    try:
        slot_budget.acquire(1, temporary)
    except world_console.RequestBodyError as error:
        require(error.status == 503, "concurrent upload limit returned the wrong status")
    else:
        raise AssertionError("multipart concurrent upload limit was not enforced")
    first.release()
    first.release()
    require(slot_budget.active_count == 0, "multipart upload slot was not released exactly once")
    require(slot_budget.reserved_bytes == 0, "multipart spool reservation was not released")

    byte_budget = world_console.MultipartSpoolBudget(2, 100, 0)
    first = byte_budget.acquire(60, temporary)
    try:
        byte_budget.acquire(50, temporary)
    except world_console.RequestBodyError as error:
        require(error.status == 503, "aggregate multipart byte limit returned the wrong status")
    else:
        raise AssertionError("aggregate multipart byte limit was not enforced")
    first.release()
    second = byte_budget.acquire(100, temporary)
    second.release()
    require(byte_budget.reserved_bytes == 0, "multipart byte budget was not reusable")

    disk_budget = world_console.MultipartSpoolBudget(1, 100, 50)
    with mock.patch.object(world_console.shutil, "disk_usage", return_value=mock.Mock(free=109)):
        try:
            disk_budget.acquire(60, temporary)
        except world_console.RequestBodyError as error:
            require(error.status == 507, "low temporary disk space returned the wrong status")
        else:
            raise AssertionError("low temporary disk space was not rejected")
    require(disk_budget.active_count == 0, "failed disk-space reservation leaked an upload slot")


def check_multipart_streaming_and_cleanup(temporary):
    boundary = b"CodexBoundary20260824"
    false_delimiter = b"\r\n--" + boundary + b"-not-a-delimiter\r\n"
    large_data = (b"streamed-data-" * 170000) + false_delimiter
    body = multipart_payload(boundary, [
        ([
            ("Content-Disposition", 'form-data; name="files"; filename="large.bin"'),
            ("Content-Type", "application/octet-stream"),
        ], large_data),
    ])

    with mock.patch.object(world_console.tempfile, "tempdir", str(temporary)):
        handler = multipart_handler(body, boundary)
        files = handler.read_multipart_files(len(body) + 1)
        require(len(files) == 1, "multipart file parser did not return exactly one file")
        data = files[0]["data"]
        require(
            isinstance(data, world_console.MultipartFileData),
            "large multipart file was materialized in memory instead of using a temp-backed slice",
        )
        require(data.size == len(large_data), "temp-backed multipart file size changed")
        with data.open() as source:
            require(source.read() == large_data, "temp-backed multipart file contents changed")
            require(source.seek(10) == 10 and source.read(7) == large_data[10:17], "multipart slice is not seekable")
        copied_path = Path(temporary) / "multipart-consumer-copy.bin"
        world_console.write_uploaded_data(copied_path, data)
        require(copied_path.read_bytes() == large_data, "multipart consumer did not stream the temp-backed file")
        temp_path = data.path
        require(temp_path.is_file(), "multipart temp file disappeared before the consumer finished")
        require(
            handler.rfile.read_sizes
            and all(0 < size <= world_console.MULTIPART_READ_CHUNK_BYTES for size in handler.rfile.read_sizes),
            f"multipart request reads were not bounded: {handler.rfile.read_sizes}",
        )
        handler._cleanup_multipart_temp_files()
        require(not temp_path.exists(), "multipart temp file was not deleted after request cleanup")

        manifest = '{"project":"example.blend","name":"Reference"}'
        form_body = multipart_payload(boundary, [
            ([
                ("Content-Disposition", 'form-data; name="manifest"'),
            ], manifest.encode("utf-8")),
            ([
                ("Content-Disposition", 'form-data; name="image.front"; filename="front.png"'),
                ("Content-Type", "image/png"),
            ], large_data),
        ])
        form_handler = multipart_handler(form_body, boundary)
        fields, form_files = form_handler.read_multipart_form(len(form_body) + 1)
        require(fields == {"manifest": manifest}, "multipart reference manifest changed")
        require(
            len(form_files) == 1
            and form_files[0]["field"] == "image.front"
            and isinstance(form_files[0]["data"], world_console.MultipartFileData),
            "reference multipart form did not preserve its temp-backed file",
        )
        form_temp_path = form_files[0]["data"].path
        form_handler._cleanup_multipart_temp_files()
        require(not form_temp_path.exists(), "reference multipart temp file was not cleaned up")

        truncated_handler = multipart_handler(body, boundary, length=len(body) + 7)
        try:
            truncated_handler.read_multipart_files(len(body) + 16)
        except world_console.RequestBodyError as error:
            require("ended before Content-Length" in str(error), f"truncation error was unclear: {error}")
        else:
            raise AssertionError("truncated multipart request was accepted")
        require_no_multipart_temps(temporary, "truncated multipart request leaked a temp file")

        oversized_handler = multipart_handler(body[:32], boundary, length=1025)
        try:
            oversized_handler.read_multipart_files(1024)
        except world_console.RequestBodyError as error:
            require(error.status == 413, f"oversized multipart request returned status {error.status}")
        else:
            raise AssertionError("oversized multipart request was accepted")
        require(not oversized_handler.rfile.read_sizes, "oversized multipart body was read before its limit was rejected")
        require_no_multipart_temps(temporary, "oversized multipart request created a temp file")

        for label, duplicate_arguments in (
            ("Content-Length", {"content_lengths": [str(len(body)), str(len(body))]}),
            ("Content-Type", {"content_types": [
                f"multipart/form-data; boundary={boundary.decode('ascii')}",
                f"multipart/form-data; boundary={boundary.decode('ascii')}",
            ]}),
        ):
            duplicate_handler = multipart_handler(body, boundary, **duplicate_arguments)
            try:
                duplicate_handler.read_multipart_files(len(body) + 1)
            except world_console.RequestBodyError as error:
                require("exactly once" in str(error), f"duplicate {label} error was unclear: {error}")
            else:
                raise AssertionError(f"duplicate {label} was accepted")
            require(not duplicate_handler.rfile.read_sizes, f"duplicate {label} body was read")
            require_no_multipart_temps(temporary, f"duplicate {label} created a temp file")

        duplicate_boundary_handler = multipart_handler(
            body,
            boundary,
            content_types=[
                f"multipart/form-data; boundary={boundary.decode('ascii')}; boundary=SecondBoundary",
            ],
        )
        try:
            duplicate_boundary_handler.read_multipart_files(len(body) + 1)
        except world_console.RequestBodyError as error:
            require("duplicated" in str(error), f"duplicate boundary error was unclear: {error}")
        else:
            raise AssertionError("duplicate multipart boundary was accepted")
        require(not duplicate_boundary_handler.rfile.read_sizes, "duplicate multipart boundary body was read")
        require_no_multipart_temps(temporary, "duplicate multipart boundary created a temp file")

        transfer_handler = multipart_handler(body, boundary)
        transfer_handler.headers.add_header("Transfer-Encoding", "chunked")
        try:
            transfer_handler.read_multipart_files(len(body) + 1)
        except world_console.RequestBodyError as error:
            require("Transfer-Encoding" in str(error), f"transfer-encoding error was unclear: {error}")
        else:
            raise AssertionError("multipart Transfer-Encoding was accepted")
        require(not transfer_handler.rfile.read_sizes, "transfer-encoded multipart body was read")
        require_no_multipart_temps(temporary, "transfer-encoded multipart request created a temp file")

        class MultipartCleanupHandler(BoundaryHandler):
            observed_paths = []

            def _dispatch_POST(self):
                files = self.read_multipart_files(len(body) + 1)
                type(self).observed_paths = [item["data"].path for item in files if hasattr(item["data"], "path")]
                self.send_json({"ok": True, "files": len(files)})

        with running_server(MultipartCleanupHandler) as port:
            status, _, response_body = request(
                port,
                "POST",
                "/__multipart-cleanup-test",
                body=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode('ascii')}"},
            )
        require(status == 200 and json.loads(response_body)["files"] == 1, "multipart cleanup probe failed")
        require(MultipartCleanupHandler.observed_paths, "multipart cleanup probe did not use a temp-backed file")
        require(
            all(not path.exists() for path in MultipartCleanupHandler.observed_paths),
            "do_POST did not clean multipart temp files after its consumer returned",
        )
        require_no_multipart_temps(temporary, "successful multipart HTTP request leaked a temp file")

        failed_paths = []

        def fail_consumer(files):
            failed_paths.extend(item["data"].path for item in files if hasattr(item["data"], "path"))
            raise RuntimeError("simulated multipart consumer failure")

        with (
            mock.patch.object(world_console, "upload_wallpapers", side_effect=fail_consumer),
            running_server() as port,
        ):
            status, _, _ = request(
                port,
                "POST",
                "/api/wallpapers/upload",
                body=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode('ascii')}"},
            )
        require(status == 500, "multipart consumer failure did not return an error")
        require(failed_paths, "multipart failure cleanup probe did not use a temp-backed file")
        require(all(not path.exists() for path in failed_paths), "consumer failure leaked multipart temp files")
        require_no_multipart_temps(temporary, "failed multipart HTTP request leaked a temp file")
        require(
            world_console.MULTIPART_SPOOL_BUDGET.active_count == 0
            and world_console.MULTIPART_SPOOL_BUDGET.reserved_bytes == 0,
            "multipart request cleanup leaked the process-wide spool reservation",
        )


def check_authority_parsing():
    require(
        world_console._origin_matches_host(
            "http://127.0.0.1:8898",
            "127.0.0.1:8898",
        ),
        "IPv4 same-origin authority was rejected",
    )
    require(
        world_console._origin_matches_host(
            "http://[0:0:0:0:0:0:0:1]:8898",
            "[::1]:8898",
        ),
        "equivalent IPv6 authorities did not match",
    )
    require(
        world_console._origin_matches_host(
            "http://console-pc.local:8898",
            "CONSOLE-PC.LOCAL.:8898",
        ),
        "case-insensitive LAN hostname was rejected",
    )
    require(
        world_console._origin_matches_host("http://example.test", "example.test"),
        "default HTTP port did not match",
    )
    require(
        not world_console._origin_matches_host(
            "http://127.0.0.1:8899",
            "127.0.0.1:8898",
        ),
        "different ports were treated as same-origin",
    )
    require(
        not world_console._origin_matches_host(
            "https://127.0.0.1:8898",
            "127.0.0.1:8898",
        ),
        "different schemes were treated as same-origin",
    )
    for trusted_host in (
        "127.0.0.1:8898",
        "[::1]:8898",
        "192.168.50.25:8898",
        "[fd00::25]:8898",
        f"{socket.gethostname()}:8898",
    ):
        require(
            world_console._is_trusted_request_host(trusted_host),
            f"trusted local/LAN Host was rejected: {trusted_host}",
        )
    for untrusted_host in ("evil.example:8898", "8.8.8.8:8898", "[2001:4860:4860::8888]:8898"):
        require(
            not world_console._is_trusted_request_host(untrusted_host),
            f"public or rebindable Host was trusted: {untrusted_host}",
        )
    require(
        world_console._client_address_is_loopback("::ffff:127.0.0.1"),
        "IPv4-mapped loopback client was rejected",
    )
    require(
        not world_console._client_address_is_loopback("192.168.50.30"),
        "remote LAN client was mistaken for a local tool",
    )


def check_originless_remote_guard():
    handler = object.__new__(world_console.ConsoleHandler)
    handler.headers = http.client.HTTPMessage()
    handler.headers["Host"] = "192.168.50.25:8898"
    handler.client_address = ("192.168.50.30", 50421)
    responses = []
    handler.send_json = lambda payload, status=200: responses.append((status, payload))
    require(
        not handler.require_trusted_post_context(),
        "Origin-less remote LAN POST was accepted",
    )
    require(
        responses and responses[-1][0] == 403,
        "Origin-less remote LAN POST did not receive 403",
    )

    handler.client_address = ("127.0.0.1", 50422)
    responses.clear()
    require(
        handler.require_trusted_post_context(),
        "Origin-less loopback tool was rejected",
    )
    require(not responses, "Origin-less loopback tool unexpectedly received an error response")


def check_texture_archive_limits():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("textures/first.png", b"a" * 4096)
        archive.writestr("textures/second.jpg", b"b" * 4096)
        archive.writestr("notes/readme.txt", b"ignored")
    payload = buffer.getvalue()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        selected = world_console.validated_texture_archive_members(archive)
    require(
        [name for _, name in selected] == ["first.png", "second.jpg"],
        "valid texture archive members were not selected predictably",
    )

    checks = [
        ("MAX_TEXTURE_ARCHIVE_MEMBERS", 2, "too many members"),
        ("MAX_TEXTURE_ARCHIVE_FILE_BYTES", 4095, "member is too large"),
        ("MAX_TEXTURE_ARCHIVE_TOTAL_BYTES", 8191, "expands beyond"),
        ("MAX_TEXTURE_ARCHIVE_COMPRESSION_RATIO", 1, "compression ratio"),
    ]
    for setting, value, expected_error in checks:
        try:
            with mock.patch.object(world_console, setting, value):
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    world_console.validated_texture_archive_members(archive)
        except ValueError as error:
            require(
                expected_error in str(error),
                f"{setting} failed with an unclear error: {error}",
            )
        else:
            raise AssertionError(f"{setting} did not reject an unsafe archive")


def check_post_boundary_and_headers(port):
    calls = []

    def fake_hotkey_start():
        calls.append("start")
        return {"ok": True}

    json_headers = {"Content-Type": "application/json"}
    with mock.patch.object(world_console, "start_hotkey_listener", fake_hotkey_start):
        status, _, _ = request(
            port,
            "POST",
            "/api/hotkey/start",
            body=b"{}",
            headers={
                **json_headers,
                "Host": f"evil.example:{port}",
                "Origin": f"http://evil.example:{port}",
            },
        )
        require(status == 403, f"rebindable Host returned {status}, expected 403")
        require(not calls, "rebindable Host reached the side-effect function")

        status, _, body = request(
            port,
            "POST",
            "/api/hotkey/start",
            body=b"{}",
            headers={
                **json_headers,
                "Origin": "https://evil.example",
            },
        )
        require(status == 403, f"hostile Origin returned {status}, expected 403")
        require(not calls, "hostile Origin reached the side-effect function")
        require("Origin" in json.loads(body)["error"] or "Cross-site" in json.loads(body)["error"], "Origin rejection was unclear")

        status, _, _ = request(
            port,
            "POST",
            "/api/hotkey/start",
            body=b"{}",
            headers={
                **json_headers,
                "Sec-Fetch-Site": "cross-site",
            },
        )
        require(status == 403, f"cross-site fetch metadata returned {status}, expected 403")
        require(not calls, "cross-site fetch metadata reached the side-effect function")

        origin = f"http://127.0.0.1:{port}"
        status, response_headers, _ = request(
            port,
            "POST",
            "/api/hotkey/start",
            body=b"{}",
            headers={**json_headers, "Origin": origin},
        )
        require(status == 200, f"same-origin POST returned {status}")
        require(calls == ["start"], "same-origin POST did not reach the side-effect function once")

        lan_host = f"192.168.50.25:{port}"
        status, _, _ = request(
            port,
            "POST",
            "/api/hotkey/start",
            body=b"{}",
            headers={
                **json_headers,
                "Host": lan_host,
                "Origin": f"http://{lan_host}",
            },
        )
        require(status == 200, f"LAN same-origin POST returned {status}")
        require(calls == ["start", "start"], "LAN same-origin POST was not preserved")

        status, _, _ = request(
            port,
            "POST",
            "/api/hotkey/start",
            body=b"{}",
            headers=json_headers,
        )
        require(status == 200, f"Origin-less native-style POST returned {status}")
        require(calls == ["start", "start", "start"], "Origin-less local tool compatibility regressed")

        status, response = raw_status(port, [
            "Content-Type: application/json",
            f"Content-Length: {world_console.MAX_JSON_REQUEST_BYTES + 1}",
        ])
        require(status == 413, f"oversized JSON returned {status}, expected 413")
        response_body = response.split(b"\r\n\r\n", 1)[1]
        require(
            "too large" in json.loads(response_body)["error"].casefold(),
            "413 response did not explain the limit",
        )
        require(calls == ["start", "start", "start"], "oversized JSON reached the side-effect function")

        status, response = raw_status(port, [])
        require(status == 411, f"missing Content-Length returned {status}, expected 411")
        require(b"Content-Length" in response, "missing-length response was unclear")

        status, response = raw_status(port, ["Content-Length: invalid"])
        require(status == 400, f"invalid Content-Length returned {status}, expected 400")
        require(b"non-negative decimal integer" in response, "invalid-length response was unclear")

    expected_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "permissions-policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        "x-permitted-cross-domain-policies": "none",
    }
    for name, expected in expected_headers.items():
        require(response_headers.get(name) == expected, f"security header {name} is missing or incorrect")


def check_streaming_response(port, temporary):
    stream_path = Path(temporary) / "stream-test.bin"
    expected = bytes(range(251)) * ((world_console.FILE_RESPONSE_CHUNK_BYTES * 2 // 251) + 2)
    stream_path.write_bytes(expected)
    BoundaryHandler.stream_path = stream_path
    read_sizes = []
    original_open = Path.open

    def tracked_open(path, *args, **kwargs):
        source = original_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(path) == stream_path and mode == "rb":
            return TrackingReader(source, read_sizes)
        return source

    def reject_read_bytes(_path):
        raise AssertionError("send_file_response used Path.read_bytes instead of streaming")

    with (
        mock.patch.object(Path, "open", tracked_open),
        mock.patch.object(Path, "read_bytes", reject_read_bytes),
    ):
        status, headers, body = request(port, "GET", "/__stream-test")

    require(status == 200, f"streaming response returned {status}")
    require(body == expected, "streaming response body changed")
    require(int(headers["content-length"]) == len(expected), "streaming Content-Length is incorrect")
    require(len(read_sizes) >= 3, "large file was not read in multiple chunks")
    require(
        max(read_sizes) == world_console.FILE_RESPONSE_CHUNK_BYTES
        and all(0 < size <= world_console.FILE_RESPONSE_CHUNK_BYTES for size in read_sizes),
        f"file reads were not bounded to {world_console.FILE_RESPONSE_CHUNK_BYTES} bytes: {read_sizes}",
    )


def check_static_cache_policy(port):
    immutable = "public, max-age=31536000, immutable"

    def require_cache_control(install_mode, path, expected):
        with mock.patch.object(world_console, "APP_INSTALL_MODE", install_mode):
            status, headers, _ = request(port, "GET", path)
        require(status == 200, f"cache test request returned {status}: {path}")
        require(
            headers.get("cache-control") == expected,
            f"{install_mode} cache policy for {path} was {headers.get('cache-control')!r}, expected {expected!r}",
        )

    for development_mode in ("source", "development"):
        require_cache_control(development_mode, "/styles.css?v=development-key", "no-cache")
    for deployed_mode in ("installed", "portable", "store"):
        require_cache_control(deployed_mode, "/styles.css?v=release-key", immutable)

    require_cache_control("installed", "/styles.css", "no-cache")
    require_cache_control("installed", "/styles.css?v=", "no-cache")
    require_cache_control("installed", "/index.html?v=release-key", "no-store")


def check_idle_connection_timeout():
    timeout = 0.2
    with running_server(connection_idle_timeout=timeout) as port:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            client.settimeout(2)
            client.sendall(
                (
                    "GET / HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                ).encode("ascii")
            )
            started = time.monotonic()
            response = client.recv(1)
            elapsed = time.monotonic() - started
        require(not response, "incomplete request was not closed after its idle timeout")
        require(
            elapsed < 1.5,
            f"idle request occupied a connection too long ({elapsed:.2f}s)",
        )

        status, _, _ = request(port, "GET", "/")
        require(status == 200, f"server did not recover after an idle request timed out ({status})")


def check_request_thread_limit():
    started = threading.Event()
    release = threading.Event()
    handler_calls = []

    class HoldingHandler(BoundaryHandler):
        def do_GET(self):
            if urllib.parse.urlparse(self.path).path == "/__hold-test":
                handler_calls.append(self.client_address)
                started.set()
                if not release.wait(timeout=5):
                    self.send_json({"error": "test request was not released"}, status=500)
                    return
                self.send_json({"ok": True})
                return
            super().do_GET()

    first_result = {}

    def run_first_request(port):
        try:
            first_result["response"] = request(port, "GET", "/__hold-test")
        except Exception as error:
            first_result["error"] = error

    with running_server(HoldingHandler, max_request_threads=1) as port:
        first_thread = threading.Thread(
            target=run_first_request,
            args=(port,),
            daemon=True,
        )
        first_thread.start()
        try:
            require(started.wait(2), "first request did not occupy the only request slot")
            overload_started = time.monotonic()
            overload_closed = False
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                    client.settimeout(2)
                    try:
                        client.sendall(
                            (
                                "GET /__hold-test HTTP/1.1\r\n"
                                f"Host: 127.0.0.1:{port}\r\n"
                                "Connection: close\r\n\r\n"
                            ).encode("ascii")
                        )
                        overload_closed = not client.recv(1)
                    except (ConnectionAbortedError, ConnectionResetError):
                        overload_closed = True
            except (ConnectionAbortedError, ConnectionResetError):
                overload_closed = True
            overload_elapsed = time.monotonic() - overload_started
            require(overload_closed, "request above the thread limit was left open")
            require(
                overload_elapsed < 1.5,
                f"overload connection was not closed immediately ({overload_elapsed:.2f}s)",
            )
            require(len(handler_calls) == 1, "overload request started another handler thread")
        finally:
            release.set()
            first_thread.join(timeout=5)

        require(not first_thread.is_alive(), "request thread did not finish after release")
        require("error" not in first_result, f"admitted request failed: {first_result.get('error')}")
        require(first_result.get("response", (None,))[0] == 200, "admitted request did not finish normally")

        status, _, _ = request(port, "GET", "/")
        require(status == 200, f"released request slot was not reusable ({status})")


def main():
    check_authority_parsing()
    check_originless_remote_guard()
    check_texture_archive_limits()
    with tempfile.TemporaryDirectory(prefix="codex-http-boundary-") as temporary:
        check_multipart_spool_budget(temporary)
        check_multipart_streaming_and_cleanup(temporary)
        with running_server() as port:
            check_post_boundary_and_headers(port)
            check_streaming_response(port, temporary)
            check_static_cache_policy(port)
    check_idle_connection_timeout()
    check_request_thread_limit()
    print("PASS HTTP boundary, multipart streaming, cache policy, idle timeout, thread limit, headers, and streaming files")


if __name__ == "__main__":
    main()
