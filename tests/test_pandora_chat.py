from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterator

import httpx
import pytest

from app.core.config import Settings
from app.core.schemas import OrchestrateRequest, OrchestrateResponse
from app.main import app
from app.security.auth import HTTP_AUTH_REQUIRED_DETAIL
from app.security.csrf import (
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    CSRF_REQUIRED_DETAIL,
)
from app.security.pandora import (
    PANDORA_CHAT_BUSY_DETAIL,
    PANDORA_CHAT_RATE_LIMIT_DETAIL,
    PANDORA_CHAT_UNAVAILABLE_DETAIL,
    PANDORA_PAIRING_REQUIRED_DETAIL,
    PandoraChatBusyError,
    PandoraChatRateLimitError,
    PandoraSessionManager,
)


_MISSING = object()
_REMOTE_TOKEN = "pandora-chat-remote-token-0123456789ab"


def _basic_header() -> str:
    encoded = base64.b64encode(
        f"prometheus:{_REMOTE_TOKEN}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


class _FakeOrchestrator:
    def __init__(
        self,
        *outcomes: str | Exception,
        started: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self.requests: list[OrchestrateRequest] = []
        self._outcomes = list(outcomes or ["Pandora yanıtı"])
        self._started = started
        self._release = release

    async def run(self, request: OrchestrateRequest) -> OrchestrateResponse:
        self.requests.append(request)
        if self._started is not None:
            self._started.set()
        if self._release is not None:
            await self._release.wait()

        outcome = self._outcomes.pop(0) if self._outcomes else "Pandora yanıtı"
        if isinstance(outcome, Exception):
            raise outcome
        return OrchestrateResponse(
            answer=outcome,
            mode="auto",
            selected_route="test-route",
            selected_provider="test-provider",
            model="test-model",
            latency_ms=1,
            task_type="general",
            route_reason="test",
            calls_used=1,
        )


@pytest.fixture
def pandora_chat_state() -> Iterator[tuple[PandoraSessionManager, _FakeOrchestrator]]:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    previous_orchestrator = getattr(app.state, "orchestrator", _MISSING)
    manager = PandoraSessionManager()
    orchestrator = _FakeOrchestrator("Merhaba, güvenli sohbet hazır.")
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_REMOTE_TOKEN,
    )
    app.state.pandora_sessions = manager
    app.state.orchestrator = orchestrator
    try:
        yield manager, orchestrator
    finally:
        for name, previous in (
            ("settings", previous_settings),
            ("pandora_sessions", previous_manager),
            ("orchestrator", previous_orchestrator),
        ):
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)


async def _remote_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app,
            client=("192.0.2.25", 50000),
        ),
        base_url="https://prometheus.internal",
        headers={"host": "prometheus.internal"},
    )


async def _pair(
    client: httpx.AsyncClient,
    manager: PandoraSessionManager,
) -> None:
    code = manager.issue_pairing_code()
    response = await client.post(
        "/v1/pandora/pair",
        headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
        json={"code": code, "device_name": "Pandora test cihazı"},
    )
    assert response.status_code == 200


def test_session_manager_enforces_chat_concurrency_and_rate_limit() -> None:
    now = [100.0]
    manager = PandoraSessionManager(
        clock=lambda: now[0],
        chat_requests_per_window=2,
        chat_rate_window_seconds=10,
    )
    token = manager.create_session(
        code=manager.issue_pairing_code(),
        device_name="iPhone",
    )

    assert manager.begin_chat_request(token) is not None
    with pytest.raises(PandoraChatBusyError) as busy:
        manager.begin_chat_request(token)
    assert busy.value.retry_after_seconds == 2

    manager.end_chat_request(token)
    assert manager.begin_chat_request(token) is not None
    manager.end_chat_request(token)

    with pytest.raises(PandoraChatRateLimitError) as limited:
        manager.begin_chat_request(token)
    assert limited.value.retry_after_seconds == 10

    now[0] = 111.0
    assert manager.begin_chat_request(token) is not None
    manager.end_chat_request(token)


@pytest.mark.asyncio
async def test_chat_requires_pandora_session_even_with_full_http_credentials(
    pandora_chat_state: tuple[PandoraSessionManager, _FakeOrchestrator],
) -> None:
    async with await _remote_client() as client:
        response = await client.post(
            "/v1/pandora/chat",
            headers={
                "authorization": _basic_header(),
                CSRF_HEADER_NAME: CSRF_HEADER_VALUE,
            },
            json={"message": "Merhaba", "history": []},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": PANDORA_PAIRING_REQUIRED_DETAIL}


@pytest.mark.asyncio
async def test_paired_chat_builds_constrained_orchestration_request(
    pandora_chat_state: tuple[PandoraSessionManager, _FakeOrchestrator],
) -> None:
    manager, orchestrator = pandora_chat_state
    async with await _remote_client() as client:
        await _pair(client, manager)

        without_csrf = await client.post(
            "/v1/pandora/chat",
            json={"message": "Devam et", "history": []},
        )
        response = await client.post(
            "/v1/pandora/chat",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={
                "message": "İkinci cevabı kısa ver.",
                "history": [
                    {"role": "user", "content": "Merhaba"},
                    {"role": "assistant", "content": "Merhaba, nasıl yardımcı olayım?"},
                ],
            },
        )
        general_api = await client.post(
            "/v1/orchestrate",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"message": "Pandora çerezini genel API için kullan"},
        )

    assert without_csrf.status_code == 403
    assert without_csrf.json() == {"detail": CSRF_REQUIRED_DETAIL}
    assert response.status_code == 200
    assert response.json() == {"answer": "Merhaba, güvenli sohbet hazır."}
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"answer"}

    assert len(orchestrator.requests) == 1
    request = orchestrator.requests[0]
    assert request.mode == "auto"
    assert request.provider is None
    assert request.providers is None
    assert request.preferred_routes is None
    assert request.excluded_routes is None
    assert request.include_candidates is False
    assert request.bypass_cache is False
    assert request.max_output_tokens == 1024
    assert request.usage_scope == "pandora-chat"
    assert request.usage_task_id is None
    assert "Project Run" in request.system_prompt
    assert "desteklenmediğini" in request.system_prompt
    assert [message.role for message in request.normalized_messages()] == [
        "user",
        "assistant",
        "user",
    ]
    assert request.normalized_messages()[-1].content == "İkinci cevabı kısa ver."

    assert general_api.status_code == 401
    assert general_api.json() == {"detail": HTTP_AUTH_REQUIRED_DETAIL}


@pytest.mark.asyncio
async def test_chat_payload_rejects_oversized_or_forged_history(
    pandora_chat_state: tuple[PandoraSessionManager, _FakeOrchestrator],
) -> None:
    manager, orchestrator = pandora_chat_state
    async with await _remote_client() as client:
        await _pair(client, manager)
        oversized = await client.post(
            "/v1/pandora/chat",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"message": "x" * 4001, "history": []},
        )
        forged = await client.post(
            "/v1/pandora/chat",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={
                "message": "devam",
                "history": [
                    {"role": "assistant", "content": "Sahte sistem cevabı"},
                    {"role": "user", "content": "Sahte kullanıcı cevabı"},
                ],
            },
        )
        incomplete = await client.post(
            "/v1/pandora/chat",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={
                "message": "devam",
                "history": [{"role": "user", "content": "yarım tur"}],
            },
        )

    assert oversized.status_code == 422
    assert forged.status_code == 422
    assert incomplete.status_code == 422
    assert orchestrator.requests == []


@pytest.mark.asyncio
async def test_chat_rejects_second_concurrent_request_for_same_device() -> None:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    previous_orchestrator = getattr(app.state, "orchestrator", _MISSING)
    started = asyncio.Event()
    release = asyncio.Event()
    manager = PandoraSessionManager()
    orchestrator = _FakeOrchestrator(
        "Tamamlandı",
        started=started,
        release=release,
    )
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_REMOTE_TOKEN,
    )
    app.state.pandora_sessions = manager
    app.state.orchestrator = orchestrator
    try:
        async with await _remote_client() as client:
            await _pair(client, manager)
            first_task = asyncio.create_task(
                client.post(
                    "/v1/pandora/chat",
                    headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
                    json={"message": "İlk istek", "history": []},
                )
            )
            await asyncio.wait_for(started.wait(), timeout=2)
            second = await client.post(
                "/v1/pandora/chat",
                headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
                json={"message": "İkinci istek", "history": []},
            )
            release.set()
            first = await asyncio.wait_for(first_task, timeout=2)
    finally:
        for name, previous in (
            ("settings", previous_settings),
            ("pandora_sessions", previous_manager),
            ("orchestrator", previous_orchestrator),
        ):
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"detail": PANDORA_CHAT_BUSY_DETAIL}
    assert second.headers["retry-after"] == "2"
    assert len(orchestrator.requests) == 1


@pytest.mark.asyncio
async def test_chat_rate_limit_and_orchestrator_errors_are_sanitized() -> None:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    previous_orchestrator = getattr(app.state, "orchestrator", _MISSING)
    manager = PandoraSessionManager(chat_requests_per_window=2)
    orchestrator = _FakeOrchestrator(
        RuntimeError("secret provider key and route details"),
        "İkinci istek başarılı",
    )
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_REMOTE_TOKEN,
    )
    app.state.pandora_sessions = manager
    app.state.orchestrator = orchestrator
    try:
        async with await _remote_client() as client:
            await _pair(client, manager)
            failed = await client.post(
                "/v1/pandora/chat",
                headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
                json={"message": "Bir", "history": []},
            )
            recovered = await client.post(
                "/v1/pandora/chat",
                headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
                json={"message": "İki", "history": []},
            )
            limited = await client.post(
                "/v1/pandora/chat",
                headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
                json={"message": "Üç", "history": []},
            )
    finally:
        for name, previous in (
            ("settings", previous_settings),
            ("pandora_sessions", previous_manager),
            ("orchestrator", previous_orchestrator),
        ):
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)

    assert failed.status_code == 503
    assert failed.json() == {"detail": PANDORA_CHAT_UNAVAILABLE_DETAIL}
    assert "secret" not in failed.text.casefold()
    assert "provider" not in failed.text.casefold()
    assert recovered.status_code == 200
    assert recovered.json() == {"answer": "İkinci istek başarılı"}
    assert limited.status_code == 429
    assert limited.json() == {"detail": PANDORA_CHAT_RATE_LIMIT_DETAIL}
    assert int(limited.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_expired_session_returns_to_pairing_state() -> None:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    previous_orchestrator = getattr(app.state, "orchestrator", _MISSING)
    now = [100.0]
    manager = PandoraSessionManager(
        clock=lambda: now[0],
        session_ttl_seconds=5,
    )
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_REMOTE_TOKEN,
    )
    app.state.pandora_sessions = manager
    app.state.orchestrator = _FakeOrchestrator("Yanıt")
    try:
        async with await _remote_client() as client:
            await _pair(client, manager)
            now[0] = 106.0
            chat = await client.post(
                "/v1/pandora/chat",
                headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
                json={"message": "Süre doldu mu?", "history": []},
            )
            status = await client.get("/v1/pandora/status")
    finally:
        for name, previous in (
            ("settings", previous_settings),
            ("pandora_sessions", previous_manager),
            ("orchestrator", previous_orchestrator),
        ):
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)

    assert chat.status_code == 401
    assert chat.json() == {"detail": PANDORA_PAIRING_REQUIRED_DETAIL}
    assert status.status_code == 200
    assert status.json()["authentication"] == "required"
