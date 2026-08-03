from __future__ import annotations

import base64
import binascii
import secrets
from typing import Any

from fastapi import Request


HTTP_AUTH_USERNAME = "prometheus"
HTTP_AUTH_REQUIRED_DETAIL = "HTTP kimlik doğrulaması gerekli."
HTTP_REMOTE_AUTH_NOT_CONFIGURED_DETAIL = (
    "Uzak HTTP erişimi için en az 32 karakterlik HTTP_AUTH_TOKEN "
    "yapılandırılmalı."
)
HTTP_AUTH_CHALLENGE = 'Basic realm="Prometheus", charset="UTF-8"'


def configured_http_auth_token(value: Any) -> str:
    if value is None:
        return ""

    reveal = getattr(value, "get_secret_value", None)
    raw = reveal() if callable(reveal) else value
    return str(raw).strip()


def _basic_password(encoded_credentials: str) -> str | None:
    try:
        decoded = base64.b64decode(
            encoded_credentials,
            validate=True,
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None

    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    if not secrets.compare_digest(
        username.encode("utf-8"),
        HTTP_AUTH_USERNAME.encode("utf-8"),
    ):
        return None
    return password


def request_http_credential(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()
    scheme, separator, credentials = authorization.partition(" ")
    if not separator or not credentials.strip():
        return None

    normalized_scheme = scheme.casefold()
    candidate = credentials.strip()
    if normalized_scheme == "bearer":
        return candidate
    if normalized_scheme == "basic":
        return _basic_password(candidate)
    return None


def request_has_valid_http_credentials(
    request: Request,
    *,
    expected_token: str,
) -> bool:
    candidate = request_http_credential(request)
    if candidate is None or not expected_token:
        return False
    return secrets.compare_digest(
        candidate.encode("utf-8"),
        expected_token.encode("utf-8"),
    )
