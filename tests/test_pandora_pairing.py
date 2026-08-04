from __future__ import annotations

import base64
from collections.abc import Iterator

import httpx
import pytest

from app.core.config import Settings
from app.main import app
from app.security.auth import HTTP_AUTH_REQUIRED_DETAIL
from app.security.csrf import (
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    CSRF_REQUIRED_DETAIL,
)
from app.security.pandora import (
    PANDORA_DEVICE_LIMIT_DETAIL,
    PANDORA_PAIRING_INVALID_DETAIL,
    PANDORA_PAIRING_LOCAL_ONLY_DETAIL,
    PANDORA_PAIRING_REQUIRED_DETAIL,
    PANDORA_REMOTE_ACCESS_REQUIRED_DETAIL,
    PANDORA_SESSION_COOKIE_NAME,
    PANDORA_SESSION_COOKIE_PATH,
    PandoraDeviceLimitError,
    PandoraPairingRejectedError,
    PandoraSessionManager,
)


_MISSING = object()
_REMOTE_TOKEN = "pandora-remote-token-0123456789abcdef"


def _basic_header() -> str:
    encoded = base64.b64encode(
        f"prometheus:{_REMOTE_TOKEN}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


@pytest.fixture
def remote_pandora_state() -> Iterator[PandoraSessionManager]:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    manager = PandoraSessionManager()
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_REMOTE_TOKEN,
    )
    app.state.pandora_sessions = manager
    try:
        yield manager
    finally:
        if previous_settings is _MISSING:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
        if previous_manager is _MISSING:
            delattr(app.state, "pandora_sessions")
        else:
            app.state.pandora_sessions = previous_manager


async def _local_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app,
            client=("127.0.0.1", 50000),
        ),
        base_url="http://localhost",
        headers={"host": "localhost:8000"},
    )


async def _remote_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app,
            client=("192.0.2.10", 50000),
        ),
        base_url="https://prometheus.internal",
        headers={"host": "prometheus.internal"},
    )


def test_pairing_code_is_single_use_and_session_can_be_revoked() -> None:
    manager = PandoraSessionManager()
    code = manager.issue_pairing_code()

    token = manager.create_session(code=code, device_name="iPhone")

    assert manager.session_for_token(token) is not None
    assert manager.active_session_count() == 1
    with pytest.raises(PandoraPairingRejectedError):
        manager.create_session(code=code, device_name="Replay")

    assert manager.revoke(token) is True
    assert manager.session_for_token(token) is None
    assert manager.revoke(token) is False


def test_pairing_code_and_session_expire() -> None:
    now = [100.0]
    manager = PandoraSessionManager(
        clock=lambda: now[0],
        pairing_ttl_seconds=5,
        session_ttl_seconds=10,
    )
    expired_code = manager.issue_pairing_code()
    now[0] = 106.0

    with pytest.raises(PandoraPairingRejectedError):
        manager.create_session(code=expired_code, device_name="Expired")

    live_code = manager.issue_pairing_code()
    token = manager.create_session(code=live_code, device_name="iPhone")
    now[0] = 117.0

    assert manager.session_for_token(token) is None
    assert manager.active_session_count() == 0


def test_wrong_pairing_attempts_invalidate_code() -> None:
    manager = PandoraSessionManager(max_pairing_attempts=2)
    code = manager.issue_pairing_code()

    for wrong_code in ("000000", "999999"):
        if wrong_code == code:
            wrong_code = "111111"
        with pytest.raises(PandoraPairingRejectedError):
            manager.create_session(code=wrong_code, device_name="Attacker")

    with pytest.raises(PandoraPairingRejectedError):
        manager.create_session(code=code, device_name="iPhone")


def test_device_limit_is_enforced() -> None:
    manager = PandoraSessionManager(max_devices=1)
    first_code = manager.issue_pairing_code()
    manager.create_session(code=first_code, device_name="First")
    second_code = manager.issue_pairing_code()

    with pytest.raises(PandoraDeviceLimitError, match=PANDORA_DEVICE_LIMIT_DETAIL):
        manager.create_session(code=second_code, device_name="Second")


@pytest.mark.asyncio
async def test_remote_shell_is_public_but_non_pandora_api_stays_protected(
    remote_pandora_state: PandoraSessionManager,
) -> None:
    async with await _remote_client() as client:
        shell = await client.get("/pandora")
        status = await client.get("/v1/pandora/status")
        root = await client.get("/")

    assert shell.status_code == 200
    assert status.status_code == 200
    assert status.json()["authentication"] == "required"
    assert root.status_code == 401
    assert root.json() == {"detail": HTTP_AUTH_REQUIRED_DETAIL}


@pytest.mark.asyncio
async def test_local_code_pairs_remote_device_with_scoped_httponly_cookie(
    remote_pandora_state: PandoraSessionManager,
) -> None:
    async with await _local_client() as local:
        code_response = await local.post(
            "/v1/pandora/pairing-code",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
        )
    code = code_response.json()["code"]

    async with await _remote_client() as remote:
        pair_response = await remote.post(
            "/v1/pandora/pair",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"code": code, "device_name": "Reşat'ın iPhone'u"},
        )
        status = await remote.get("/v1/pandora/status")
        cookie_value = pair_response.cookies.get(PANDORA_SESSION_COOKIE_NAME)
        root = await remote.get(
            "/",
            headers={
                "cookie": f"{PANDORA_SESSION_COOKIE_NAME}={cookie_value}",
            },
        )

    assert code_response.status_code == 200
    assert code_response.headers["cache-control"] == "no-store"
    assert pair_response.status_code == 200
    assert pair_response.json()["authentication"] == "pandora"
    set_cookie = pair_response.headers["set-cookie"]
    assert f"{PANDORA_SESSION_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Secure" in set_cookie
    assert f"Path={PANDORA_SESSION_COOKIE_PATH}" in set_cookie
    assert status.status_code == 200
    assert status.json()["authentication"] == "pandora"
    assert root.status_code == 401
    assert root.json() == {"detail": HTTP_AUTH_REQUIRED_DETAIL}


@pytest.mark.asyncio
async def test_pairing_and_logout_require_csrf(
    remote_pandora_state: PandoraSessionManager,
) -> None:
    code = remote_pandora_state.issue_pairing_code()
    async with await _remote_client() as remote:
        pair_without_csrf = await remote.post(
            "/v1/pandora/pair",
            json={"code": code, "device_name": "iPhone"},
        )
        pair = await remote.post(
            "/v1/pandora/pair",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"code": code, "device_name": "iPhone"},
        )
        logout_without_csrf = await remote.post("/v1/pandora/logout")
        logout = await remote.post(
            "/v1/pandora/logout",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
        )
        status = await remote.get("/v1/pandora/status")

    assert pair_without_csrf.status_code == 403
    assert pair_without_csrf.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert pair.status_code == 200
    assert logout_without_csrf.status_code == 403
    assert logout_without_csrf.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert logout.status_code == 204
    assert status.json()["authentication"] == "required"


@pytest.mark.asyncio
async def test_invalid_pairing_code_is_rejected_without_cookie(
    remote_pandora_state: PandoraSessionManager,
) -> None:
    issued_code = remote_pandora_state.issue_pairing_code()
    invalid_code = "000000" if issued_code != "000000" else "999999"
    async with await _remote_client() as remote:
        response = await remote.post(
            "/v1/pandora/pair",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"code": invalid_code, "device_name": "Unknown"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": PANDORA_PAIRING_INVALID_DETAIL}
    assert PANDORA_SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_pairing_code_endpoint_is_local_only_even_with_full_credentials(
    remote_pandora_state: PandoraSessionManager,
) -> None:
    async with await _remote_client() as remote:
        response = await remote.post(
            "/v1/pandora/pairing-code",
            headers={
                "authorization": _basic_header(),
                CSRF_HEADER_NAME: CSRF_HEADER_VALUE,
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": PANDORA_PAIRING_LOCAL_ONLY_DETAIL}


@pytest.mark.asyncio
async def test_protected_pandora_route_requires_pairing(
    remote_pandora_state: PandoraSessionManager,
) -> None:
    async with await _remote_client() as remote:
        response = await remote.post(
            "/v1/pandora/logout",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": PANDORA_PAIRING_REQUIRED_DETAIL}


@pytest.mark.asyncio
async def test_pairing_code_requires_remote_access_to_be_enabled() -> None:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    app.state.settings = Settings(_env_file=None)
    app.state.pandora_sessions = PandoraSessionManager()
    try:
        async with await _local_client() as local:
            response = await local.post(
                "/v1/pandora/pairing-code",
                headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            )
    finally:
        if previous_settings is _MISSING:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
        if previous_manager is _MISSING:
            delattr(app.state, "pandora_sessions")
        else:
            app.state.pandora_sessions = previous_manager

    assert response.status_code == 409
    assert response.json() == {"detail": PANDORA_REMOTE_ACCESS_REQUIRED_DETAIL}
