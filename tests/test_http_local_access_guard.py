from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.security.network import REMOTE_ACCESS_DISABLED_DETAIL


_MISSING = object()
_REMOTE_TOKEN = "remote-access-token-0123456789abcdef"


async def _request_root(
    *,
    client_host: str,
    host_header: str,
    remote_access_enabled: bool = False,
    authorization: str | None = None,
) -> httpx.Response:
    previous_settings = getattr(app.state, "settings", _MISSING)
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=remote_access_enabled,
        http_auth_token=(
            _REMOTE_TOKEN if remote_access_enabled else None
        ),
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
            return await client.get(
                "/",
                headers=headers,
            )
    finally:
        if previous_settings is _MISSING:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_host", "host_header"),
    [
        ("127.0.0.1", "127.0.0.1:8000"),
        ("::1", "[::1]:8000"),
        ("127.0.0.1", "localhost:8000"),
        ("::ffff:127.0.0.1", "localhost"),
    ],
)
async def test_loopback_requests_are_allowed(
    client_host: str,
    host_header: str,
) -> None:
    response = await _request_root(
        client_host=client_host,
        host_header=host_header,
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_remote_client_is_blocked_by_default() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="localhost:8000",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": REMOTE_ACCESS_DISABLED_DETAIL,
    }


@pytest.mark.asyncio
async def test_non_loopback_host_header_is_blocked() -> None:
    response = await _request_root(
        client_host="127.0.0.1",
        host_header="attacker.example",
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": REMOTE_ACCESS_DISABLED_DETAIL,
    }


@pytest.mark.asyncio
async def test_explicit_remote_access_opt_in_bypasses_guard() -> None:
    response = await _request_root(
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        remote_access_enabled=True,
        authorization=f"Bearer {_REMOTE_TOKEN}",
    )

    assert response.status_code == 200


def test_starlette_testclient_sentinel_is_allowed() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
