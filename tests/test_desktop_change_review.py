from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.main import read_desktop_approval_review


def _command(*, mission_id="mission-1", approval_id="approval-1", state="pending", preview=None):
    task = SimpleNamespace(id="task-1", title="Review change", approval_id=approval_id, approval_version=2, approval_state=state, approval_tool="workspace_write", approval_description="User review required.", approval_preview=preview)
    return SimpleNamespace(id=mission_id, tasks=[task])


@pytest.mark.asyncio
async def test_review_requires_exact_mission_and_approval(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command(mission_id=command_id)
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_desktop_approval_review("mission-1", "approval-1")
    assert result.mission_id == "mission-1" and result.approval_id == "approval-1"


@pytest.mark.asyncio
async def test_cross_mission_substitution_fails_closed(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command(mission_id="mission-2")
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc: await read_desktop_approval_review("mission-1", "approval-1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cross_approval_substitution_fails_closed(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command()
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc: await read_desktop_approval_review("mission-1", "other")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_canonical_preview_and_binding_are_reused(monkeypatch):
    preview = {"plan_id": "plan-1", "preview_id": "preview-1", "affected_files": ["app/main.py"], "operations": [{"kind": "replace"}], "before": "old", "after": "new"}
    class Supervisor:
        async def get(self, command_id): return _command(preview=preview)
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_desktop_approval_review("mission-1", "approval-1")
    assert result.preview == preview and result.affected_files == ["app/main.py"] and result.operation_count == 1


@pytest.mark.asyncio
async def test_missing_review_artifact_is_truthful(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command(preview=None)
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_desktop_approval_review("mission-1", "approval-1")
    assert result.preview is None and result.unavailable_reason


@pytest.mark.asyncio
async def test_stale_approval_fails_closed(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command(state="applied")
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc: await read_desktop_approval_review("mission-1", "approval-1")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_review_bounds_large_preview_and_marks_truncated(monkeypatch):
    preview = {"affected_files": [f"file-{i}.py" for i in range(150)], "operations": [{"kind": "replace"} for _ in range(150)], "content": "x" * 130_000}
    class Supervisor:
        async def get(self, command_id): return _command(preview=preview)
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    result = await read_desktop_approval_review("mission-1", "approval-1")
    assert result.truncated is True and len(result.preview or {}) == 1


@pytest.mark.asyncio
async def test_invalid_approval_identifier_does_not_fallback(monkeypatch):
    class Supervisor:
        async def get(self, command_id): return _command()
    from app import main
    monkeypatch.setattr(main.app.state, "supervisor", Supervisor(), raising=False)
    with pytest.raises(HTTPException) as exc: await read_desktop_approval_review("mission-1", "")
    assert exc.value.status_code == 404
