"""Render a LAN entrance with an optional short-lived, one-use QR invitation."""
import io
import ipaddress
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

import qrcode
from qrcode.image.pil import PilImage


def connection_qr_png(state, *, use_ip=False):
    if not state.get("enabled"):
        raise ValueError("请先开启手机入口。")
    base = state.get("url", "") if use_ip else state.get("connectionUrl") or state.get("url", "")
    parsed = urlsplit(base)
    try:
        port = parsed.port
        hostname = parsed.hostname or ""
    except (ValueError, TypeError):
        raise ValueError("手机连接地址无效。") from None
    try:
        address = ipaddress.IPv4Address(hostname)
        private = any(address in ipaddress.ip_network(network) for network in
                      ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    except ValueError:
        discovery = state.get("discovery") or {}
        private = (not use_ip and discovery.get("available") is True and
                   hostname == discovery.get("hostname") and
                   bool(re.fullmatch(r"codex-[a-f0-9]{12,32}\.local", hostname)))
    if (parsed.scheme != "http" or not private or not port or parsed.username or
            parsed.password or parsed.path not in {"", "/", "/mobile.html"} or
            parsed.query or parsed.fragment):
        raise ValueError("请使用电脑的同 Wi-Fi 手机地址。")
    invitation = state.get("ipQrUrl" if use_ip else "qrUrl")
    if invitation:
        invite = urlsplit(invitation)
        if (invite.scheme != "http" or invite.netloc != parsed.netloc or invite.path != "/" or
                invite.query != "tab=transfer" or invite.username or invite.password):
            raise ValueError("扫码连接地址无效。")
        fragment = invite.fragment
    else:
        token = state.get("qrToken", "")
        fragment = "qrToken=" + token if token else ""
    if fragment:
        values = parse_qs(fragment, strict_parsing=True, max_num_fields=1)
        if (set(values) != {"qrToken"} or len(values["qrToken"]) != 1 or
                not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", values["qrToken"][0]) or
                state.get("qrToken") and values["qrToken"][0] != state["qrToken"]):
            raise ValueError("扫码邀请无效，请生成新二维码。")
    target = urlunsplit(("http", parsed.netloc, "/", "tab=transfer", fragment))
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
    code.add_data(target)
    code.make(fit=True)
    image = code.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
