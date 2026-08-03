from __future__ import annotations

import base64
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.security.auth import (
    HTTP_AUTH_CHALLENGE,
    HTTP_AUTH_REQUIRED_DETAIL,
    HTTP_REMOTE_AUTH_NOT_CONFIGURED_DETAIL,
)


_MISSING = object()
_VALID_TOKEN = "prometheus-remote-token-0123456789abcdef"


def _basic_header(*, username: str, password: str) -> str:
    encoded = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


async def _request_root(
    *,
    client_host: str,
    host_header: str,
    authorization: str | None = None,
    settings: object | None = None,
) -> httpx.Response:
    previous_settings = getattr(app.state, "settings", _MISSING)
    app.state.settings = settings or Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_VALID_TOKEN,
    )
    transport = httpx.ASGITransport(
        app=app,
        client=(client_host, 50000),
    )

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            headers = {"host": host_header}
            if authorization is not None:
                headers["authorization"] = authorization
            return await client.get("/", headers=headers)
    finally:
        if previous_settings is _MISSING:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings


def test_remote_access_requires_a_configured_token() -> None:
    with pytest.raises(
        ValidationError,
        match="HTTP_AUTH_TOKEN",
    ):
        Settings(
            _env_file=None,
            http_remote_access_enabled=True,
        )


@pytest.mark.parametrize(
    "token",
    ["", "short-token", "x" * 31],
)
def test_remote_access_rejects_short_tokens(token: str) -> None:
    with pytest.raises(
        ValidationError,
        match="en az 32 karakter",
    ):
        Settings(
            _env_file=None,
            http_remote_access_enabled=True,
            http_auth_token=token,
        )


def test_configured_token_is_masked_in_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_VALID_TOKEN,
    )

    assert _VALID_TOKEN not in repr(settings)


@pytest.mark.asyncio
async def test_remote_request_without_credentials_is_unauthorized() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": HTTP_AUTH_REQUIRED_DETAIL,
    }
    assert response.headers["www-authenticate"] == HTTP_AUTH_CHALLENGE


@pytest.mark.asyncio
async def test_wrong_bearer_token_is_unauthorized_and_not_echoed() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization="Bearer wrong-token",
    )

    assert response.status_code == 401
    assert _VALID_TOKEN not in response.text
    assert "wrong-token" not in response.text


@pytest.mark.asyncio
async def test_valid_bearer_token_allows_remote_api_access() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization=f"Bearer {_VALID_TOKEN}",
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_valid_basic_credentials_allow_browser_access() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization=_basic_header(
            username="prometheus",
            password=_VALID_TOKEN,
        ),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_basic_credentials_require_fixed_username() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization=_basic_header(
            username="admin",
            password=_VALID_TOKEN,
        ),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_remote_mode_requires_authentication_on_loopback_too() -> None:
    response = await _request_root(
        client_host="127.0.0.1",
        host_header="localhost:8000",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_authorization_header_is_unauthorized() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization="Basic not-valid-base64!",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_middleware_fails_closed_if_invalid_settings_are_injected() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        settings=SimpleNamespace(
            http_remote_access_enabled=True,
            http_auth_token=None,
        ),
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": HTTP_REMOTE_AUTH_NOT_CONFIGURED_DETAIL,
    }
