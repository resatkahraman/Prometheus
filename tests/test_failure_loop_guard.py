from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoAgent:
    pass


def task():
    return SupervisorTask(
        id="TASK-001",
        title="pytest",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["score.py", "tests/test_score.py"],
        status="running",
        autonomy_granted=True,
        materialized_files=["score.py", "tests/test_score.py"],
    )


def test_repair_target_uses_failure_path_instead_of_first_exact_file(
    tmp_path: Path,
):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    item = SupervisorTask(
        id="TASK-001",
        title="calculator",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["tests pass"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test",
        user_approval="gerekli",
        exact_files=[
            "package.json",
            "src/calculator.js",
            "tests/calculator.test.js",
        ],
    )
    result = {
        "stdout": (
            "AssertionError [ERR_ASSERTION]\n"
            "at tests\\calculator.test.js:67:10\n"
        ),
        "stderr": "",
    }

    assert service._verification_repair_path(
        task=item,
        result=result,
        failure_kind="assertion_failure",
    ) == "tests/calculator.test.js"


def test_changed_repair_state_gets_one_bounded_extra_attempt(
    tmp_path: Path,
):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    assert service._should_block_repeated_failure(
        count=2,
        limit=2,
        repair_state_changed=False,
    ) is True
    assert service._should_block_repeated_failure(
        count=2,
        limit=2,
        repair_state_changed=True,
    ) is False
    assert service._should_block_repeated_failure(
        count=3,
        limit=2,
        repair_state_changed=True,
    ) is True


@pytest.mark.asyncio
async def test_same_failure_is_blocked_after_limit(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_same_failure_limit=2,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    item = task()
    command = SupervisorCommand(
        id="cmd",
        goal="x",
        status="running",
        autonomy_mode="task",
        plan_text="",
        tasks=[item],
    )
    await service.store.put(command)
    result = {
        "exit_code": 2,
        "success": False,
        "command": ["python", "-m", "pytest", "-q"],
        "stdout": "import file mismatch pytest",
        "stderr": "",
    }

    # Mark strategy as already attempted so the first call cannot open a new
    # terminal approval and the second identical failure hits the guard.
    item.attempted_strategies.append("pytest_importlib")
    await service._run_verification_repair(
        command_id="cmd",
        task_id="TASK-001",
        result=result,
    )
    command = await service.store.get("cmd")
    command.tasks[0].status = "running"
    await service.store.put(command)
    final = await service._run_verification_repair(
        command_id="cmd",
        task_id="TASK-001",
        result=result,
    )
    assert final.tasks[0].status == "rework_required"
    assert final.tasks[0].recovery_reason == "repeated_failure_blocked"
    assert final.tasks[0].blocked_reason
