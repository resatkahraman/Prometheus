from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class ModelMustNotRun:
    async def run(self, request):
        raise AssertionError(
            "Başarılı deterministic repair sonrası model çağrılmamalı"
        )


def make_task() -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="score doğrulama",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["pytest başarılı olmalı"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["score.py", "tests/test_score.py"],
        status="ready",
        autonomy_granted=True,
    )


@pytest.mark.asyncio
async def test_successful_importlib_repair_finishes_task_without_model(
    tmp_path: Path,
):
    (tmp_path / "backend").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "score.py").write_text(
        "def calculate_score(a, b, c): return a * b + c\n",
        encoding="utf-8",
    )
    (tmp_path / "backend/test_score.py").write_text(
        "from score import calculate_score\n"
        "def test_old(): assert calculate_score(1, 2, 3) == 5\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_score.py").write_text(
        "from score import calculate_score\n"
        "def test_new(): assert calculate_score(2, 3, 4) == 10\n",
        encoding="utf-8",
    )

    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_trusted_autonomy_enabled=True,
        supervisor_persistence_enabled=False,
        supervisor_approval_background=False,
        supervisor_auto_review=True,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=ModelMustNotRun(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd",
        goal="Mevcut score özelliğini doğrula.",
        status="ready",
        autonomy_mode="trusted",
        plan_text="",
        tasks=[make_task()],
    )
    await service.store.put(command)

    result = await service.run_task(
        command_id="cmd",
        task_id="TASK-001",
        background=False,
    )

    task = result.tasks[0]
    assert task.status == "completed"
    assert task.review_answer.startswith("KABUL")
    assert "--import-mode=importlib" in task.effective_verification
    assert task.verification_strategy == "pytest_importlib"
    assert task.workspace_state_validated is True
    assert task.materialized_files == [
        "score.py",
        "tests/test_score.py",
    ]

    terminal_records = [
        record
        for record in task.approval_history
        if record.tool == "safe_terminal"
    ]
    assert len(terminal_records) == 2
    assert terminal_records[0].success is False
    assert terminal_records[1].success is True
    assert not any(
        event.type in {
            "focused_file_approval_required",
            "focused_step_incomplete",
            "repair_loop_blocked",
        }
        for event in result.events
    )


@pytest.mark.asyncio
async def test_existing_exact_files_count_as_materialized_workspace_evidence(
    tmp_path: Path,
):
    (tmp_path / "tests").mkdir()
    (tmp_path / "score.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests/test_score.py").write_text(
        "def test_x(): assert True\n",
        encoding="utf-8",
    )

    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=ModelMustNotRun(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = make_task()

    missing = await service._synchronize_workspace_evidence(task)

    assert missing == []
    assert task.workspace_state_validated is True
    assert task.materialized_files == [
        "score.py",
        "tests/test_score.py",
    ]
