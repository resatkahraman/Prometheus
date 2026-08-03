from __future__ import annotations

import secrets

from fastapi import Request


CSRF_HEADER_NAME = "X-Prometheus-CSRF"
CSRF_HEADER_VALUE = "1"
CSRF_REQUIRED_DETAIL = (
    "Durum değiştiren HTTP istekleri için "
    "X-Prometheus-CSRF: 1 başlığı gerekli."
)
SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def csrf_protection_required(request: Request) -> bool:
    return request.method.upper() not in SAFE_HTTP_METHODS


def request_has_valid_csrf_header(request: Request) -> bool:
    candidate = request.headers.get(CSRF_HEADER_NAME, "").strip()
    return secrets.compare_digest(
        candidate.encode("utf-8"),
        CSRF_HEADER_VALUE.encode("utf-8"),
    )
