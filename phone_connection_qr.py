"""Render the enabled LAN entrance locally; never encode pairing credentials."""
import io
import ipaddress
from urllib.parse import urlsplit, urlunsplit

import qrcode
from qrcode.image.pil import PilImage


def connection_qr_png(state):
    if not state.get("enabled"):
        raise ValueError("请先开启手机入口。")
    parsed = urlsplit(state.get("url", ""))
    try:
        address = ipaddress.IPv4Address(parsed.hostname)
        port = parsed.port
    except (ValueError, TypeError):
        raise ValueError("手机连接地址无效。") from None
    private = any(address in ipaddress.ip_network(network) for network in
                  ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if (parsed.scheme != "http" or not private or not port or parsed.username or
            parsed.password or parsed.path not in {"", "/", "/mobile.html"} or
            parsed.query or parsed.fragment):
        raise ValueError("请使用电脑的同 Wi-Fi 手机地址。")
    target = urlunsplit(("http", parsed.netloc, "/", "tab=transfer", ""))
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
    code.add_data(target)
    code.make(fit=True)
    image = code.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
