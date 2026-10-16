"""Let standard Git inherit the current Windows HTTP proxy, like Desktop does."""
import os
import urllib.request
from urllib.parse import urlsplit


def _windows_proxy(url):
    if os.name != "nt":
        return None
    # The stdlib reads the current user's enabled static proxy and bypass list.
    # PAC resolution belongs to the system browser; do not invent a PAC result.
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
        try:
            if winreg.QueryValueEx(key, "AutoConfigURL")[0]:
                return None
        except FileNotFoundError:
            pass
    parsed = urlsplit(url)
    if urllib.request.proxy_bypass_registry(parsed.netloc):
        return None
    return urllib.request.getproxies_registry().get(parsed.scheme.lower())


def environment_for_remote(environment, remote_url, *, resolver=None):
    """Return a copy; explicit proxy settings and Git's own config keep priority.

    No credentials, registry values or proxy addresses are logged or persisted.
    Git still owns authentication, TLS verification, hooks and LFS transport.
    """
    result = dict(environment)
    try:
        parsed = urlsplit(remote_url)
        protocol = parsed.scheme.lower()
        if protocol not in {"http", "https"} or not parsed.hostname:
            return result
        key = protocol + "_proxy"
        if ("ALL_PROXY" in result or "all_proxy" in result or key in result or key.upper() in result):
            return result
        address = (resolver or _windows_proxy)(remote_url)
        proxy = urlsplit(address) if isinstance(address, str) and len(address) <= 4096 else None
        if (proxy is not None and proxy.scheme.lower() in {"http", "https", "socks", "socks4", "socks5", "socks5h"}
                and proxy.hostname and not any(char in address for char in "\r\n\0")):
            # Access port to reject an invalid port before passing it to Git.
            proxy.port
            result[key] = address
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # Keep the normal Git environment if system resolution is unknown.
    return result
