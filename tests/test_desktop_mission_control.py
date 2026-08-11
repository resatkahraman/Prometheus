from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.schemas import SupervisorApprovalRequest
from app.main import (
    approve_supervisor_task,
    read_supervisor_command,
    read_supervisor_mission_events,
    reject_supervisor_task,
)


def _command(command_id: str = "mission-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=command_id,
        goal="Görevi yürüt",
        status="awaiting_approval",
        tasks=[],
        decisions=[],
        operation_message="Onay bekleniyor",
        plan_text="",
        failure_reason=None,
        mission_id=command_id,
    )


@pytest.mark.asyncio
async def test_desktop_mission_read_uses_canonical_supervisor(monkeypatch):
    class Supervisor:
        async def get(self, command_id):
            assert command_id == "mission-1"
            return _command()

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_supervisor_command("mission-1")
    assert result.id == "mission-1" and result.status == "awaiting_approval"


@pytest.mark.asyncio
async def test_unknown_mission_is_truthful_not_found(monkeypatch):
    class Supervisor:
        async def get(self, command_id):
            raise KeyError(command_id)

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc:
        await read_supervisor_command("missing")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mission_events_use_canonical_supervisor(monkeypatch):
    class Supervisor:
        async def list_mission_events(self, command_id, *, after_sequence, limit):
            assert command_id == "mission-1" and after_sequence == 0 and limit == 50
            return SimpleNamespace(mission_id=command_id, events=[], count=0, after_sequence=0, next_after_sequence=None, has_more=False, source="empty", integrity_verified=True, last_sequence=0, last_event_hash=None)

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_supervisor_mission_events("mission-1", after_sequence=0, limit=50)
    assert result.mission_id == "mission-1" and result.integrity_verified is True


@pytest.mark.asyncio
async def test_approval_binds_exact_identity_and_delegates(monkeypatch):
    calls = []
    class Supervisor:
        async def approve(self, **kwargs):
            calls.append(kwargs)
            return _command()

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await approve_supervisor_task("mission-1", "task-1", SupervisorApprovalRequest(approval_id="approval-1", approval_version=2))
    assert result.id == "mission-1"
    assert calls == [{"command_id": "mission-1", "task_id": "task-1", "expected_approval_id": "approval-1", "expected_approval_version": 2, "background": True}]


@pytest.mark.asyncio
async def test_rejection_binds_exact_identity_and_delegates(monkeypatch):
    calls = []
    class Supervisor:
        async def reject(self, **kwargs):
            calls.append(kwargs)
            return _command()

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    await reject_supervisor_task("mission-1", "task-1", SupervisorApprovalRequest(approval_id="approval-1", approval_version=2))
    assert calls == [{"command_id": "mission-1", "task_id": "task-1", "expected_approval_id": "approval-1", "expected_approval_version": 2}]


@pytest.mark.asyncio
async def test_stale_approval_returns_truthful_conflict(monkeypatch):
    class Supervisor:
        async def approve(self, **kwargs):
            raise ValueError("approval conflict")

    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc:
        await approve_supervisor_task("mission-1", "task-1", SupervisorApprovalRequest(approval_id="old", approval_version=1))
    assert exc.value.status_code == 400
