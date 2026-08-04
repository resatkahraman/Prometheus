from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "pandora"


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://localhost",
        headers={"host": "localhost:8000"},
    ) as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_pandora_page_is_installable_and_honest() -> None:
    response = await _get("/pandora")

    assert response.status_code == 200
    html = response.text
    for marker in (
        'lang="tr"',
        'rel="manifest" href="/static/pandora/manifest.webmanifest"',
        'name="apple-mobile-web-app-capable"',
        'name="apple-mobile-web-app-status-bar-style"',
        'name="apple-mobile-web-app-title"',
        'href="/static/pandora/app.css"',
        'src="/static/pandora/app.js"',
        "Pandora hazırlanıyor",
        "Pandora eşleştirme",
        "Gerçek sohbet",
        "Sesli görüşme, yerel ses motoru doğrulandıktan sonra açılacak.",
    ):
        assert marker in html
    assert "disabled" in html
    assert "https://" not in html
    assert "http://" not in html


@pytest.mark.asyncio
async def test_pandora_manifest_is_valid() -> None:
    response = await _get("/static/pandora/manifest.webmanifest")
    manifest = response.json()

    assert response.status_code == 200
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/pandora"
    assert manifest["scope"] == "/"
    assert json.loads((STATIC_ROOT / "manifest.webmanifest").read_text("utf-8")) == manifest


@pytest.mark.asyncio
async def test_service_worker_has_root_scope_and_safe_cache_rules() -> None:
    response = await _get("/pandora-sw.js")

    assert response.status_code == 200
    assert response.headers["service-worker-allowed"] == "/"
    source = response.text
    assert 'startsWith("/v1/")' in source
    assert 'request.method !== "GET"' in source
    assert 'request.headers.has("Authorization")' in source


@pytest.mark.asyncio
async def test_pandora_status_exposes_only_safe_fields() -> None:
    response = await _get("/v1/pandora/status")
    payload = response.json()

    assert response.status_code == 200
    assert set(payload) == {
        "service",
        "status",
        "pandora_voice",
        "authentication",
        "remote_access",
        "pairing_code_allowed",
    }
    assert payload == {
        "service": "prometheus",
        "status": "ok",
        "pandora_voice": "pending",
        "authentication": "prometheus",
        "remote_access": "disabled",
        "pairing_code_allowed": False,
    }
    assert response.headers["cache-control"] == "no-store"
    serialized = response.text.casefold()
    for forbidden in ("workspace", "provider", "model", "token", "tool", "agent", ":\\", "/users/"):
        assert forbidden not in serialized


def test_pandora_javascript_uses_safe_browser_primitives() -> None:
    source = (STATIC_ROOT / "app.js").read_text("utf-8")

    for forbidden in ("innerHTML", "localStorage", "sessionStorage", "setInterval"):
        assert forbidden not in source
    assert "textContent" in source
    assert 'const PROMETHEUS_CSRF_HEADER = "X-Prometheus-CSRF"' in source
    assert 'const PROMETHEUS_CSRF_VALUE = "1"' in source
    assert 'const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"])' in source
    assert '"/v1/pandora/pairing-code"' in source
    assert '"/v1/pandora/pair"' in source
    assert '"/v1/pandora/logout"' in source
    assert 'credentials: "same-origin"' in source
