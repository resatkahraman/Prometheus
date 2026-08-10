from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.main import app
from app.security.network import is_local_http_request, request_is_verified_tailscale_serve


TOKEN = "remote-access-token-0123456789abcdef"
ORIGIN = "https://pandora.example.ts.net"
USER = "device@example.test"


def strict_settings(**overrides):
    values = {"_env_file": None, "http_remote_access_enabled": True, "http_auth_token": TOKEN, "http_remote_access_mode": "tailscale_serve", "http_remote_tailscale_user": USER, "http_remote_external_origin": ORIGIN}
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_non_loopback_forged_serve_headers_are_blocked():
    previous = getattr(app.state, "settings", None)
    app.state.settings = strict_settings()
    try:
        transport = httpx.ASGITransport(app=app, client=("192.0.2.20", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.get("/v1/cache", headers={"host": "pandora.example.ts.net", "Tailscale-User-Login": USER, "authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 403
    finally:
        app.state.settings = previous


def test_strict_configuration_requires_identity_and_https_origin():
    with pytest.raises(ValueError):
        strict_settings(http_remote_tailscale_user=None)
    with pytest.raises(ValueError):
        strict_settings(http_remote_external_origin="http://pandora.example.ts.net")
    assert Settings(_env_file=None).http_remote_access_mode == "direct"


def test_verified_transport_requires_loopback_peer_and_exact_identity():
    request = type("Request", (), {})()
    assert request_is_verified_tailscale_serve(request, None) is False
    assert is_local_http_request
