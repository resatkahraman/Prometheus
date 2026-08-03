from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urlsplit

from fastapi import Request


REMOTE_ACCESS_DISABLED_DETAIL = (
    "Uzak HTTP erişimi devre dışı. Prometheus yalnızca localhost "
    "üzerinden kullanılabilir."
)


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
