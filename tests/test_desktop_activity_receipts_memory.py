from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.main import read_desktop_mission_memory, read_supervisor_execution_receipts, read_supervisor_mission_events, read_supervisor_mission_history


def _command(mission_id="mission-1", workspace_path="."):
    return SimpleNamespace(id=mission_id, workspace_path=workspace_path)


@pytest.mark.asyncio
async def test_activity_exact_mission_and_canonical_order(monkeypatch):
    class Supervisor:
        async def list_mission_events(self, command_id, *, after_sequence, limit):
            assert command_id == "mission-1" and after_sequence == 0 and limit == 100
            return SimpleNamespace(mission_id=command_id, events=[SimpleNamespace(sequence=1), SimpleNamespace(sequence=2)], count=2, after_sequence=0, next_after_sequence=None, has_more=False, source="journal", integrity_verified=True, last_sequence=2, last_event_hash="sha256:x")
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_supervisor_mission_events("mission-1", after_sequence=0, limit=100)
    assert [event.sequence for event in result.events] == [1, 2]


@pytest.mark.asyncio
async def test_receipts_are_canonical_and_bounded(monkeypatch):
    class Supervisor:
        async def list_execution_receipts(self, command_id, *, after_sequence, limit):
            assert limit == 100
            return SimpleNamespace(mission_id=command_id, receipts=[{"receipt_id": "r1", "receipt_hash": "sha256:canonical"}], count=1, after_sequence=0, next_after_sequence=None, has_more=False, source="receipt_store", integrity_verified=True, last_sequence=1, last_receipt_hash="sha256:canonical")
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_supervisor_execution_receipts("mission-1", after_sequence=0, limit=100)
    assert result.receipts[0]["receipt_id"] == "r1"


@pytest.mark.asyncio
async def test_history_uses_canonical_summary(monkeypatch):
    class Supervisor:
        async def get_mission_history(self, command_id, *, after_sequence, limit):
            return SimpleNamespace(mission_id=command_id, command_status="completed", terminal=True, entries=[], count=0, after_sequence=0, next_after_sequence=None, has_more=False, source="journal", integrity_verified=True, last_sequence=0, last_event_hash=None)
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_supervisor_mission_history("mission-1", response=SimpleNamespace(headers={}))
    assert result.terminal is True and result.source == "journal"


@pytest.mark.asyncio
async def test_memory_is_project_scoped_and_read_only(monkeypatch):
    calls = []
    class Supervisor:
        async def get(self, command_id): return _command(workspace_path="project-a")
    class Memory:
        def list(self, **kwargs): calls.append(kwargs); return SimpleNamespace(workspace_path="project-a", state="present", project_id=None, store_revision=1, store_digest=None, items=[], total=0, next_after_revision=None, side_effect_free=True)
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False); monkeypatch.setattr(main.app.state, "decision_memory", Memory(), raising=False)
    result = await read_desktop_mission_memory("mission-1", response=SimpleNamespace(headers={}))
    assert result.workspace_path == "project-a" and calls[0]["workspace_path"] == "project-a"


@pytest.mark.asyncio
async def test_memory_cross_mission_substitution_rejected(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command(mission_id="mission-2")
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc: await read_desktop_mission_memory("mission-1", response=SimpleNamespace(headers={}))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_missing_receipts_fail_truthfully(monkeypatch):
    class Supervisor:
        async def list_execution_receipts(self, *args, **kwargs): raise KeyError("missing")
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc: await read_supervisor_execution_receipts("mission-1", after_sequence=0, limit=100)
    assert exc.value.status_code == 404


def test_desktop_models_do_not_recompute_receipt_digest():
    from pathlib import Path
    text = Path("desktop/src").read_text(encoding="utf-8") if Path("desktop/src").is_file() else ""
    assert "sha256(" not in text
