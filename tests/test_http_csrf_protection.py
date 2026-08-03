from __future__ import annotations

import base64
from types import SimpleNamespace

import httpx
import pytest

from app.antigravity_ui import ANTIGRAVITY_UI
from app.chat_ui import CHAT_UI
from app.command_ui import COMMAND_UI
from app.core.config import Settings
from app.lab_ui import LAB_UI
from app.main import app
from app.security.auth import HTTP_AUTH_REQUIRED_DETAIL
from app.security.csrf import (
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    CSRF_REQUIRED_DETAIL,
)


_MISSING = object()
_VALID_TOKEN = "prometheus-remote-token-0123456789abcdef"


class _CacheStore:
    def __init__(self) -> None:
        self.clear_calls = 0

    async def clear_cache(self) -> int:
        self.clear_calls += 1
        return 7


def _basic_header(*, username: str, password: str) -> str:
    encoded = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


async def _request(
    method: str,
    path: str,
    *,
    remote_access_enabled: bool = False,
    authorization: str | None = None,
    csrf_value: str | None = None,
    client_host: str = "127.0.0.1",
    host_header: str = "localhost:8000",
) -> tuple[httpx.Response, _CacheStore]:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_store = getattr(app.state, "store", _MISSING)
    store = _CacheStore()
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=remote_access_enabled,
        http_auth_token=(
            _VALID_TOKEN if remote_access_enabled else None
        ),
    )
    app.state.store = store
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
            if csrf_value is not None:
                headers[CSRF_HEADER_NAME] = csrf_value
            response = await client.request(
                method,
                path,
                headers=headers,
            )
            return response, store
    finally:
        if previous_settings is _MISSING:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
        if previous_store is _MISSING:
            delattr(app.state, "store")
        else:
            app.state.store = previous_store


@pytest.mark.asyncio
async def test_safe_get_request_does_not_require_csrf_header() -> None:
    response, _store = await _request("GET", "/")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_local_mutation_without_csrf_header_is_blocked() -> None:
    response, store = await _request("DELETE", "/v1/cache")

    assert response.status_code == 403
    assert response.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert store.clear_calls == 0


@pytest.mark.asyncio
async def test_wrong_csrf_header_value_is_blocked() -> None:
    response, store = await _request(
        "DELETE",
        "/v1/cache",
        csrf_value="wrong",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert store.clear_calls == 0


@pytest.mark.asyncio
async def test_local_mutation_with_csrf_header_is_allowed() -> None:
    response, store = await _request(
        "DELETE",
        "/v1/cache",
        csrf_value=CSRF_HEADER_VALUE,
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 7}
    assert store.clear_calls == 1


@pytest.mark.asyncio
async def test_remote_basic_auth_still_requires_csrf_header() -> None:
    response, store = await _request(
        "DELETE",
        "/v1/cache",
        remote_access_enabled=True,
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization=_basic_header(
            username="prometheus",
            password=_VALID_TOKEN,
        ),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert store.clear_calls == 0


@pytest.mark.asyncio
async def test_remote_bearer_auth_still_requires_csrf_header() -> None:
    response, store = await _request(
        "DELETE",
        "/v1/cache",
        remote_access_enabled=True,
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization=f"Bearer {_VALID_TOKEN}",
    )

    assert response.status_code == 403
    assert response.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert store.clear_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [
        f"Bearer {_VALID_TOKEN}",
        _basic_header(
            username="prometheus",
            password=_VALID_TOKEN,
        ),
    ],
)
async def test_remote_authenticated_mutation_with_csrf_header_is_allowed(
    authorization: str,
) -> None:
    response, store = await _request(
        "DELETE",
        "/v1/cache",
        remote_access_enabled=True,
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
        authorization=authorization,
        csrf_value=CSRF_HEADER_VALUE,
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 7}
    assert store.clear_calls == 1


@pytest.mark.asyncio
async def test_authentication_failure_precedes_csrf_failure() -> None:
    response, store = await _request(
        "DELETE",
        "/v1/cache",
        remote_access_enabled=True,
        client_host="192.0.2.10",
        host_header="prometheus.internal:8000",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": HTTP_AUTH_REQUIRED_DETAIL}
    assert store.clear_calls == 0


@pytest.mark.asyncio
async def test_invalid_runtime_auth_configuration_precedes_csrf() -> None:
    previous_settings = getattr(app.state, "settings", _MISSING)
    app.state.settings = SimpleNamespace(
        http_remote_access_enabled=True,
        http_auth_token=None,
    )
    transport = httpx.ASGITransport(
        app=app,
        client=("192.0.2.10", 50000),
    )

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            response = await client.delete(
                "/v1/cache",
                headers={"host": "prometheus.internal:8000"},
            )
    finally:
        if previous_settings is _MISSING:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_options_request_is_not_csrf_blocked() -> None:
    response, _store = await _request("OPTIONS", "/v1/cache")

    assert response.status_code != 403


def test_all_browser_uis_install_csrf_fetch_wrapper() -> None:
    for html in (
        ANTIGRAVITY_UI,
        CHAT_UI,
        COMMAND_UI,
        LAB_UI,
    ):
        assert 'const PROMETHEUS_CSRF_HEADER="X-Prometheus-CSRF";' in html
        assert 'headers.set(PROMETHEUS_CSRF_HEADER,PROMETHEUS_CSRF_VALUE);' in html
        assert 'new Set(["GET","HEAD","OPTIONS"])' in html
