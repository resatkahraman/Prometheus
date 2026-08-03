from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.supervisor.contract_repair import build_fastapi_status_code_repair
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.workspace.policy import WorkspacePolicy


_CONTRACT = '''from fastapi.testclient import TestClient
from src.task_api import create_app


def test_create_contract():
    client = TestClient(create_app())
    created = client.post("/tasks", json={"title": "one"})
    assert created.status_code == 201
    assert client.get("/tasks").status_code == 200
'''

_SOURCE = '''from fastapi import FastAPI


def create_app():
    app = FastAPI()

    @app.post("/tasks")
    def create_task():
        return {"id": 1}

    @app.get("/tasks")
    def list_tasks():
        return []

    return app
'''

_FAILURE = '''tests/test_task_api_backend_contract.py:12: AssertionError
>       assert created.status_code == 201
E       assert 200 == 201
E        +  where 200 = <Response [200 OK]>.status_code
'''


def test_adds_missing_fastapi_status_code_from_pytest_contract():
    repair = build_fastapi_status_code_repair(
        target_path="src/task_api.py",
        target_source=_SOURCE,
        contract_sources=[_CONTRACT],
        failure_output=_FAILURE,
    )

    assert repair is not None
    assert '@app.post("/tasks", status_code=201)' in repair.content
    assert '@app.get("/tasks")' in repair.content
    assert repair.changes == ("POST /tasks: 200 -> 201",)


def test_replaces_wrong_literal_status_code():
    source = _SOURCE.replace('@app.post("/tasks")', '@app.post("/tasks", status_code=202)')
    repair = build_fastapi_status_code_repair(
        target_path="src/task_api.py",
        target_source=source,
        contract_sources=[_CONTRACT],
        failure_output=_FAILURE,
    )

    assert repair is not None
    assert 'status_code=201' in repair.content
    assert 'status_code=202' not in repair.content


def test_does_not_rewrite_already_correct_source():
    source = _SOURCE.replace('@app.post("/tasks")', '@app.post("/tasks", status_code=201)')
    assert build_fastapi_status_code_repair(
        target_path="src/task_api.py",
        target_source=source,
        contract_sources=[_CONTRACT],
        failure_output=_FAILURE,
    ) is None


def test_requires_explicit_status_code_failure_evidence():
    assert build_fastapi_status_code_repair(
        target_path="src/task_api.py",
        target_source=_SOURCE,
        contract_sources=[_CONTRACT],
        failure_output="assert response.json() == expected",
    ) is None


def test_conflicting_contract_statuses_are_not_repaired():
    conflicting = _CONTRACT + '''\n\ndef test_conflict():\n    client = TestClient(create_app())\n    response = client.post("/tasks", json={"title": "two"})\n    assert response.status_code == 202\n'''
    assert build_fastapi_status_code_repair(
        target_path="src/task_api.py",
        target_source=_SOURCE,
        contract_sources=[conflicting],
        failure_output=_FAILURE,
    ) is None


class _Store:
    def __init__(self, command: SupervisorCommand) -> None:
        self.command = command

    async def put(self, command: SupervisorCommand) -> None:
        self.command = command


@pytest.mark.asyncio
async def test_supervisor_selects_deterministic_repair_without_model_call(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/task_api.py").write_text(_SOURCE, encoding="utf-8")
    (tmp_path / "tests/test_task_api_backend_contract.py").write_text(
        _CONTRACT,
        encoding="utf-8",
    )

    task = SupervisorTask(
        id="TASK-001",
        title="FastAPI backend",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["POST /tasks HTTP 201 döndürmeli."],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification=(
            "python -m pytest -q "
            "tests/test_task_api_backend_contract.py"
        ),
        user_approval="gerekli",
        exact_files=["src/task_api.py"],
        status="running",
    )
    command = SupervisorCommand(
        id="cmd-contract-repair",
        goal="FastAPI görev API",
        status="running",
        plan_text="",
        tasks=[task],
    )

    service = SupervisorService.__new__(SupervisorService)
    service.settings = Settings(_env_file=None, workspace_root=tmp_path)
    service.workspace = WorkspacePolicy(
        root=tmp_path,
        max_file_bytes=100_000,
        max_search_results=20,
    )
    service.store = _Store(command)
    service._set_supervisor_pending_approval = AsyncMock(
        return_value=(True, None)
    )
    service._advance_structured_task = AsyncMock()

    result = await service._try_deterministic_contract_repair(
        command=command,
        task=task,
        result={
            "success": False,
            "stdout": _FAILURE,
            "stderr": "",
        },
        failure_kind="assertion_failure",
    )

    assert result is command
    service._set_supervisor_pending_approval.assert_awaited_once()
    call = service._set_supervisor_pending_approval.await_args.kwargs
    assert call["tool_name"] == "workspace_write"
    assert call["arguments"]["path"] == "src/task_api.py"
    assert 'status_code=201' in call["arguments"]["content"]
    assert any(
        event.type == "deterministic_contract_repair_selected"
        for event in command.events
    )
    service._advance_structured_task.assert_not_awaited()
