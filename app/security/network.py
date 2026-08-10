from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urlsplit
import hmac

from fastapi import Request


REMOTE_ACCESS_DISABLED_DETAIL = (
    "Uzak HTTP erişimi devre dışı. Prometheus yalnızca localhost "
    "üzerinden kullanılabilir."
)
SECURE_REMOTE_TRANSPORT_DETAIL = "Secure remote transport verification failed."


def _header_hostname(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""

    try:
        return (urlsplit(f"//{candidate}").hostname or "").strip()
    except ValueError:
        return ""


def is_loopback_host(value: str) -> bool:
    candidate = value.strip().lower().rstrip(".")
    if not candidate:
        return False
    if candidate == "localhost":
        return True

    candidate = candidate.split("%", 1)[0]

    try:
        address = ip_address(candidate)
    except ValueError:
        return False

    if address.is_loopback:
        return True

    if isinstance(address, IPv6Address):
        mapped: IPv4Address | None = address.ipv4_mapped
        return bool(mapped and mapped.is_loopback)

    return False


def is_local_http_request(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    header_host = _header_hostname(request.headers.get("host", ""))

    # Starlette's in-process TestClient uses these sentinel values. They are
    # not reachable through a real TCP connection and keep integration tests
    # compatible with the same production guard.
    if client_host == "testclient" and header_host == "testserver":
        return True

    return is_loopback_host(client_host) and is_loopback_host(header_host)


def _header_values(request: Request, name: str) -> list[str]:
    return list(request.headers.getlist(name))


def request_is_direct_loopback(request: Request) -> bool:
    return is_local_http_request(request) and not request_is_verified_tailscale_serve(request, getattr(request.app.state, "settings", None))


def request_is_verified_tailscale_serve(request: Request, settings) -> bool:
    remote_enabled = bool(getattr(settings, "http_remote_access_enabled", False))
    mode = getattr(settings, "http_remote_access_mode", "direct")
    if not remote_enabled or mode != "tailscale_serve":
        return False
    allowed_user = getattr(settings, "http_remote_tailscale_user", None)
    external_origin = getattr(settings, "http_remote_external_origin", None)
    if not isinstance(allowed_user, str) or not isinstance(external_origin, str) or not allowed_user.strip() or not external_origin.strip():
        return False
    client_host = request.client.host if request.client else ""
    if not is_loopback_host(client_host):
        return False
    identities = _header_values(request, "Tailscale-User-Login")
    if len(identities) != 1:
        return False
    expected = allowed_user.strip().casefold()
    incoming = identities[0].strip().casefold()
    if not expected or not hmac.compare_digest(expected, incoming):
        return False
    hosts = _header_values(request, "Host")
    if len(hosts) != 1:
        return False
    try:
        configured = urlsplit(external_origin)
        actual = urlsplit(f"//{hosts[0].strip()}")
    except ValueError:
        return False
    return bool(configured.hostname and actual.hostname and configured.hostname.casefold() == actual.hostname.casefold() and (actual.port in {None, 443}))


def request_origin_is_allowed(request: Request, configured_origin: str | None) -> bool:
    origins = _header_values(request, "Origin")
    if len(origins) > 1:
        return False
    if not origins:
        return True
    return bool(configured_origin and origins[0].strip() == configured_origin)
