"""Read only public-page metadata on an explicit request; never fetch media."""
from __future__ import annotations

from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

MAX_HTML_BYTES = 1024 * 1024
NETWORK_TIMEOUT = 8
MAX_DNS_BYTES = 64 * 1024
FAKE_IP_NETWORK = ipaddress.ip_network('198.18.0.0/15')
DOH_HOST = 'cloudflare-dns.com'
DOH_ADDRESS = '1.1.1.1'


def _is_public_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (address.is_global and not address.is_multicast
            and not getattr(address, 'is_site_local', False))


class ResourcePreviewError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def public_url(value):
    if not isinstance(value, str) or len(value) > 4096 or re.search(r"[\x00-\x20\\]", value):
        raise ResourcePreviewError("请输入完整的公开 HTTPS 网页地址。")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (ValueError, UnicodeError):
        raise ResourcePreviewError("网页地址无效。") from None
    if (parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or host.endswith((".localhost", ".local", ".internal")) or "." not in host):
        raise ResourcePreviewError("仅支持公开 HTTPS 网页地址。")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not _is_public_address(host):
        raise ResourcePreviewError("不能预览本机或内网地址。")
    return urlunsplit(("https", f"[{host}]" if ":" in host else host,
                       parsed.path or "/", parsed.query, ""))


def resolve_public(host):
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    except OSError:
        raise ResourcePreviewError("网站地址暂时无法解析，可以保留链接并手动填写名称。", 502) from None
    # Some VPNs return only synthetic addresses from the benchmarking range.
    # Never connect to those addresses or grant that range a public exemption.
    # Ask one fixed, TLS-authenticated resolver for real addresses instead.
    if addresses and all(_is_fake_address(address) for address in addresses):
        addresses = _resolve_fake_dns(host)
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ResourcePreviewError("不能预览本机、内网或受限制的地址。")
    return addresses


def _is_fake_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and address in FAKE_IP_NETWORK


def _resolve_fake_dns(host):
    addresses = []
    for kind in (1, 28):
        connection = _PinnedHTTPS(DOH_HOST, DOH_ADDRESS)
        try:
            connection.request('GET', '/dns-query?' + urlencode({'name': host, 'type': kind}), headers={
                'User-Agent': 'CodexConsole/1.0 ResourcePreview',
                'Accept': 'application/dns-json', 'Accept-Encoding': 'identity',
            })
            response = connection.getresponse()
            if response.status != 200:
                raise ResourcePreviewError('可信 DNS 暂时无法读取，未连接到网站。', 502)
            content_type = response.getheader('Content-Type', '').split(';', 1)[0].strip().lower()
            if content_type not in ('application/dns-json', 'application/json'):
                raise ResourcePreviewError('可信 DNS 返回格式无效，未连接到网站。', 502)
            data = response.read(MAX_DNS_BYTES + 1)
            if len(data) > MAX_DNS_BYTES:
                raise ResourcePreviewError('可信 DNS 回应过大，未连接到网站。', 502)
            document = json.loads(data)
            questions = document.get('Question') if isinstance(document, dict) else None
            if (not isinstance(document, dict) or type(document.get('Status')) is not int
                    or document['Status'] != 0 or document.get('TC') is not False
                    or not isinstance(questions, list) or len(questions) != 1
                    or not isinstance(questions[0], dict)
                    or type(questions[0].get('type')) is not int or questions[0]['type'] != kind
                    or not isinstance(questions[0].get('name'), str)
                    or questions[0]['name'].rstrip('.').lower() != host.rstrip('.').lower()):
                raise ResourcePreviewError('可信 DNS 回应与查询不符，未连接到网站。', 502)
            answers = document.get('Answer', [])
            if not isinstance(answers, list) or len(answers) > 128:
                raise ResourcePreviewError('可信 DNS 地址列表无效，未连接到网站。', 502)
            for answer in answers:
                if not isinstance(answer, dict) or type(answer.get('type')) is not int:
                    raise ResourcePreviewError('可信 DNS 地址记录无效，未连接到网站。', 502)
                if answer['type'] not in (1, 28):
                    continue
                address = answer.get('data')
                if not isinstance(address, str) or not _is_public_address(address):
                    raise ResourcePreviewError('不能预览本机、内网或受限制的地址。')
                if ipaddress.ip_address(address).version != (4 if answer['type'] == 1 else 6):
                    raise ResourcePreviewError('可信 DNS 地址类型无效，未连接到网站。', 502)
                if address not in addresses:
                    addresses.append(address)
        except ResourcePreviewError:
            raise
        except (OSError, http.client.HTTPException, UnicodeError, ValueError):
            raise ResourcePreviewError('可信 DNS 暂时无法解析，请稍后重试或手动填写资料。', 502) from None
        finally:
            connection.close()
    if not addresses:
        raise ResourcePreviewError('可信 DNS 没有公开网站地址，请检查链接。', 502)
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Validate DNS once and pin the connection while retaining TLS hostname checks."""
    def __init__(self, hostname, address):
        super().__init__(hostname, timeout=NETWORK_TIMEOUT, context=ssl.create_default_context())
        self._public_address = address

    def connect(self):
        plain = socket.create_connection((self._public_address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(plain, server_hostname=self.host)
        except BaseException:
            plain.close()
            raise


class PageMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self.in_title = {}, [], False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() != "meta":
            return
        values = {str(key).lower(): value for key, value in attrs}
        name = str(values.get("property") or values.get("name") or "").lower()
        value = values.get("content")
        if name and isinstance(value, str) and name not in self.meta:
            self.meta[name] = value[:8192]

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and len(self.title) < 20:
            self.title.append(data[:1024])


def fetch_metadata(value):
    url = public_url(value)
    for _ in range(4):
        parsed = urlsplit(url)
        address = resolve_public(parsed.hostname)[0]
        connection = _PinnedHTTPS(parsed.hostname, address)
        try:
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            connection.request("GET", path, headers={
                "User-Agent": "CodexConsole/1.0 ResourcePreview",
                "Accept": "text/html,application/xhtml+xml", "Accept-Encoding": "identity",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ResourcePreviewError("网站跳转缺少地址，请手动添加链接。", 502)
                url = public_url(urljoin(url, location))
                continue
            if response.status != 200:
                raise ResourcePreviewError(f"网站返回 HTTP {response.status}，未读取预览。可在原站查看后手动填写。", 502)
            content_type = response.getheader("Content-Type", "").lower()
            if not content_type.startswith(("text/html", "application/xhtml+xml")):
                raise ResourcePreviewError("该链接不是可读取的网页，请填写资源介绍页。")
            data = response.read(MAX_HTML_BYTES + 1)
            if len(data) > MAX_HTML_BYTES:
                raise ResourcePreviewError("网页过大，未读取预览。可保留链接并手动填写。", 502)
            encoding_match = re.search(r"charset=([\w-]+)", content_type)
            encoding = encoding_match[1] if encoding_match else "utf-8"
            try:
                text = data.decode(encoding, errors="replace")
            except LookupError:
                text = data.decode("utf-8", errors="replace")
            metadata = PageMetadata()
            metadata.feed(text)
            fields = metadata.meta
            title = fields.get("og:title") or fields.get("twitter:title") or " ".join(metadata.title)
            description = fields.get("og:description") or fields.get("description") or fields.get("twitter:description") or ""
            image = fields.get("og:image") or fields.get("twitter:image") or ""
            preview = ""
            if image:
                try:
                    preview = public_url(urljoin(url, image.strip()))
                    resolve_public(urlsplit(preview).hostname)
                except ResourcePreviewError:
                    preview = ""
            return {"name": re.sub(r"\s+", " ", title).strip()[:200] or parsed.hostname,
                    "url": url, "previewUrl": preview,
                    "description": re.sub(r"\s+", " ", description).strip()[:2000],
                    "warning": "" if preview else "此页未提供可读取的预览图，可手动添加原站图片地址。"}
        except ResourcePreviewError:
            raise
        except (OSError, http.client.HTTPException, UnicodeError):
            raise ResourcePreviewError("网站暂时无法读取，可以保留链接并手动填写名称及图片。", 502) from None
        finally:
            connection.close()
    raise ResourcePreviewError("网站跳转过多，未读取预览。请使用最终资源页面链接。", 502)
