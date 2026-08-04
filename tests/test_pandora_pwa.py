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
        "Pandora bağlantı bekliyor",
        "Pandora eşleştirme",
        "Pandora metin sohbeti",
        'id="chat-form"',
        'maxlength="4000"',
        'id="project-run-card"',
        'id="project-run-form"',
        'maxlength="2000"',
        "Planı masaüstü onayına gönder",
        "Mobilde yalnız plan hazırlanır",
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
    assert 'const CACHE_NAME = "pandora-shell-v4"' in source
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
        "pandora_chat",
        "pandora_project_run",
        "authentication",
        "remote_access",
        "pairing_code_allowed",
    }
    assert payload == {
        "service": "prometheus",
        "status": "ok",
        "pandora_voice": "pending",
        "pandora_chat": "ready",
        "pandora_project_run": "ready",
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
    assert '"/v1/pandora/chat"' in source
    assert '"/v1/pandora/projects"' in source
    assert '"/v1/pandora/project-run/preview"' in source
    assert '"/v1/pandora/project-run/commit"' in source
    assert '"/v1/pandora/project-run/latest"' in source
    assert '`/v1/pandora/project-run/${encodeURIComponent(activeProjectRunId)}`' in source
    assert "const CHAT_MESSAGE_MAX_CHARS = 4000" in source
    assert "const CHAT_HISTORY_MAX_MESSAGES = 12" in source
    assert "const PROJECT_RUN_GOAL_MAX_CHARS = 2000" in source
    assert "document.createElement" in source
    assert 'credentials: "same-origin"' in source
