from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.desktop_server import CORE_HOST, DEFAULT_CORE_PORT, resolve_core_port
from app.core.schemas import DesktopCommandRequest
from app.main import submit_desktop_command


def _request(client: str = "127.0.0.1", host: str = "127.0.0.1") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/v1/desktop/command", "headers": [(b"host", host.encode())], "client": (client, 1234), "query_string": b""})


def test_desktop_server_port_contract():
    assert CORE_HOST == "127.0.0.1"
    assert resolve_core_port(None) == DEFAULT_CORE_PORT == 8765
    assert resolve_core_port("4321") == 4321
    assert resolve_core_port("80") == DEFAULT_CORE_PORT
    assert resolve_core_port("not-a-port") == DEFAULT_CORE_PORT


def test_desktop_message_is_trimmed_and_bounded():
    assert DesktopCommandRequest(message="  hesapla  ").message == "hesapla"
    with pytest.raises(ValueError):
        DesktopCommandRequest(message="   ")
    with pytest.raises(ValueError):
        DesktopCommandRequest(message="x" * 20_001)


@pytest.mark.asyncio
async def test_desktop_command_uses_supervisor_ingress(monkeypatch):
    calls = []
    class Supervisor:
        async def create(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["goal"] == "hesapla"
            assert kwargs["auto_start"] is False
            assert kwargs["background"] is True
            assert kwargs["autonomy_mode"] == "task"
            assert kwargs["workspace_path"] is None
            return SimpleNamespace(id="mission-1", status="planning", tasks=[], decisions=[], operation_message="queued", plan_text="", failure_reason=None)

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await submit_desktop_command(DesktopCommandRequest(message=" hesapla "), _request())
    assert result.mission_id == "mission-1"
    assert result.status == "planning"
    assert result.requires_approval is False
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_desktop_command_normalizes_backend_summary_and_approval(monkeypatch):
    class Supervisor:
        async def create(self, **kwargs):
            return SimpleNamespace(
                id="mission-2",
                status="awaiting_approval",
                tasks=[SimpleNamespace(status="running", approval_state="pending")],
                decisions=[],
                operation_message="queued",
                plan_text="plan",
                failure_reason="failure",
            )

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await submit_desktop_command(DesktopCommandRequest(message="hesapla"), _request())
    assert result.model_dump() == {"status": "awaiting_approval", "mission_id": "mission-2", "summary": "queued", "requires_approval": True}


@pytest.mark.asyncio
async def test_desktop_command_rejects_non_loopback():
    with pytest.raises(HTTPException) as exc:
        await submit_desktop_command(DesktopCommandRequest(message="hesapla"), _request("192.168.1.10", "192.168.1.10"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_desktop_command_rejects_non_loopback_host():
    with pytest.raises(HTTPException) as exc:
        await submit_desktop_command(DesktopCommandRequest(message="hesapla"), _request("127.0.0.1", "192.168.1.10"))
    assert exc.value.status_code == 403
