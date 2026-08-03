from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.arena.catalog import get_scenario, list_scenarios
from app.arena.event_telemetry import summarize_arena_events
from app.arena.runner import ArenaRunner
from app.core.config import Settings
from app.planning.kernel import TypedPlanningKernel
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry
from app.workspace.policy import WorkspacePolicy


class _NoModelAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, request):
        self.calls += 1
        raise AssertionError("verification-first flow must not call a model")


def _task(*, exact_files: list[str]) -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="existing target",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["existing contract must pass"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q tests/test_contract.py",
        user_approval="gerekli",
        exact_files=exact_files,
        status="running",
    )


def test_existing_nonempty_targets_are_not_treated_as_missing(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src/empty.py").write_text("", encoding="utf-8")

    service = SupervisorService.__new__(SupervisorService)
    service.workspace = WorkspacePolicy(
        root=tmp_path,
        max_file_bytes=100_000,
        max_search_results=20,
    )

    assert service._next_unmaterialized_file(
        _task(exact_files=["src/existing.py"])
    ) is None
    assert service._next_unmaterialized_file(
        _task(exact_files=["src/existing.py", "src/missing.py"])
    ) == "src/missing.py"
    assert service._next_unmaterialized_file(
        _task(exact_files=["src/empty.py"])
    ) == "src/empty.py"


@pytest.mark.asyncio
async def test_planner_uses_existing_focused_contract_without_writing_test(
    tmp_path: Path,
):
    scenario = get_scenario("fastapi_status_contract_repair")
    ArenaRunner._seed(tmp_path, scenario)

    settings = Settings(_env_file=None, workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    planner = TypedPlanningKernel(tools=tools, read_max_lines=160)
    result = await planner.build(goal=scenario.goal)

    assert len(result.document.tasks) == 1
    task = result.document.tasks[0]
    assert task.assigned_agent == "backend"
    assert task.exact_files == ["src/status_api.py"]
    assert task.verification == (
        "python -m pytest -q tests/test_status_api_contract.py"
    )
    assert "tests/test_status_api_contract.py" not in task.exact_files
    assert any(
        evidence.type == "file"
        and evidence.value == "tests/test_status_api_contract.py"
        for evidence in task.evidence
    )


@pytest.mark.asyncio
async def test_existing_fastapi_contract_repairs_without_model_call(
    tmp_path: Path,
):
    scenario = get_scenario("fastapi_status_contract_repair")
    ArenaRunner._seed(tmp_path, scenario)

    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
        supervisor_trusted_autonomy_enabled=True,
        supervisor_auto_review=True,
        project_memory_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    planner = TypedPlanningKernel(tools=tools, read_max_lines=160)
    plan = await planner.build(goal=scenario.goal)
    task = SupervisorService._task_from_plan(plan.document.tasks[0])
    task.status = "running"

    agent = _NoModelAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd-verification-first",
        goal=scenario.goal,
        status="running",
        autonomy_mode="trusted",
        auto_run=False,
        plan_text=plan.text,
        tasks=[task],
        execution_layers=[[task.id]],
    )
    await service.store.put(command)

    result = await service._advance_structured_task(
        command_id=command.id,
        task_id=task.id,
        reason="test",
    )

    source = (tmp_path / "src/status_api.py").read_text(encoding="utf-8")
    event_counts, notable_events = summarize_arena_events(result.events)

    assert result.status == "completed"
    assert result.tasks[0].status == "completed"
    assert agent.calls == 0
    assert '@application.post("/items", status_code=201)' in source
    assert event_counts["existing_target_verification_first"] == 1
    assert event_counts["deterministic_contract_repair_selected"] == 1
    assert any(
        event.get("type") == "existing_target_verification_first"
        for event in notable_events
    )
    assert any(
        event.get("type") == "deterministic_contract_repair_selected"
        for event in notable_events
    )


@pytest.mark.asyncio
async def test_existing_correct_target_completes_with_zero_model_and_zero_write(
    tmp_path: Path,
):
    scenario = get_scenario("fastapi_status_contract_repair")
    ArenaRunner._seed(tmp_path, scenario)
    source_path = tmp_path / "src/status_api.py"
    source_path.write_text(
        source_path.read_text(encoding="utf-8").replace(
            '@application.post("/items")',
            '@application.post("/items", status_code=201)',
        ),
        encoding="utf-8",
    )
    before = source_path.read_bytes()

    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
        supervisor_trusted_autonomy_enabled=True,
        supervisor_auto_review=True,
        project_memory_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    planner = TypedPlanningKernel(tools=tools, read_max_lines=160)
    plan = await planner.build(goal=scenario.goal)
    task = SupervisorService._task_from_plan(plan.document.tasks[0])
    task.status = "running"

    agent = _NoModelAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd-verification-first-green",
        goal=scenario.goal,
        status="running",
        autonomy_mode="trusted",
        auto_run=False,
        plan_text=plan.text,
        tasks=[task],
        execution_layers=[[task.id]],
    )
    await service.store.put(command)

    result = await service._advance_structured_task(
        command_id=command.id,
        task_id=task.id,
        reason="test",
    )

    event_counts, _ = summarize_arena_events(result.events)
    assert result.status == "completed"
    assert result.tasks[0].status == "completed"
    assert agent.calls == 0
    assert source_path.read_bytes() == before
    assert event_counts["existing_target_verification_first"] == 1
    assert event_counts.get("deterministic_contract_repair_selected", 0) == 0
    assert not any(
        record.tool == "workspace_write"
        for record in result.tasks[0].approval_history
    )


def test_contract_repair_scenario_is_listed_with_zero_model_target():
    scenario = get_scenario("fastapi_status_contract_repair")
    assert scenario in list_scenarios()
    assert scenario.required_paths == ("src/status_api.py",)
    assert scenario.protected_paths == (
        "src/__init__.py",
        "pyproject.toml",
        "tests/test_status_api_contract.py",
    )
    assert scenario.target_model_calls == 1
    assert scenario.max_model_calls == 4
