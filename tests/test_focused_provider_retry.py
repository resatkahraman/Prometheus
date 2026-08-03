import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class TimeoutAgent:
    def __init__(self, fail_count=1, error_msg="TimeoutError: timed out"):
        self.call_count = 0
        self.fail_count = fail_count
        self.error_msg = error_msg

    async def run(self, request):
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise TimeoutError(self.error_msg)
        class PendingApproval:
            id = "appr-1"
            tool_name = "workspace_write"
            description = "Write file"
            preview = {"path": "src/task.py", "content": "print(1)"}
            expires_at = None
            arguments = {"path": "src/task.py", "content": "print(1)"}
        class Response:
            text = '{"thought": "done", "action": "workspace_write", "args": {"path": "src/task.py", "content": "print(1)"}}'
            answer = "done"
            final_route = "gemini"
            final_model = "gemini-2.0-flash"
            status = "awaiting_approval"
            session_id = "sess-1"
            pending_approval = PendingApproval()
        return Response()


class ProgrammingErrorAgent:
    async def run(self, request):
        raise ValueError("invalid internal state")


class BudgetErrorAgent:
    async def run(self, request):
        raise RuntimeError("Misyon model çağrısı bütçesi tükendi: 18/18")


class RouteUnavailableAgent:
    async def run(self, request):
        raise RuntimeError("Uygun model rotası bulunamadı")


def test_focused_provider_retry_settings():
    s1 = Settings(supervisor_focused_provider_retry_limit=1)
    assert s1.supervisor_focused_provider_retry_limit == 1

    s0 = Settings(supervisor_focused_provider_retry_limit=0)
    assert s0.supervisor_focused_provider_retry_limit == 0

    s3 = Settings(supervisor_focused_provider_retry_limit=3)
    assert s3.supervisor_focused_provider_retry_limit == 3

    with pytest.raises(ValidationError):
        Settings(supervisor_focused_provider_retry_limit=4)


@pytest.mark.asyncio
async def test_transient_retry_schedules_remote_retry_and_can_succeed(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_focused_provider_retry_limit=1,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = TimeoutAgent(fail_count=1)
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["src/task.py"],
        status="ready",
    )
    command = SupervisorCommand(
        id="cmd-retry",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    result = await service._run_focused_agent_step(
        command_id=command.id,
        task_id=task.id,
        allowed_paths=["src/task.py"],
        instruction="write task",
        phase="focused_file_generation",
    )
    assert agent.call_count == 2
    assert result.status == "awaiting_approval"
    events = [e.type for e in result.events]
    assert "focused_provider_retry_scheduled" in events
    task_after = result.tasks[0]
    assert task_after.failure_counts.get("focused_provider_transient") == 1


@pytest.mark.asyncio
async def test_transient_retry_exhausted_fails_closed(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_focused_provider_retry_limit=1,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = TimeoutAgent(fail_count=5)
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["src/task.py"],
        status="ready",
    )
    command = SupervisorCommand(
        id="cmd-exhausted",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    result = await service._run_focused_agent_step(
        command_id=command.id,
        task_id=task.id,
        allowed_paths=["src/task.py"],
        instruction="write task",
        phase="focused_file_generation",
    )
    assert agent.call_count == 2
    task_after = result.tasks[0]
    assert task_after.status == "rework_required"
    assert task_after.recovery_reason == "focused_provider_timeout"
    events = [e.type for e in result.events]
    assert "focused_provider_retry_scheduled" in events
    assert "focused_provider_retry_exhausted" in events


@pytest.mark.asyncio
async def test_retry_limit_zero_disables_retry(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_focused_provider_retry_limit=0,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = TimeoutAgent(fail_count=1)
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["src/task.py"],
        status="ready",
    )
    command = SupervisorCommand(
        id="cmd-zero",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    result = await service._run_focused_agent_step(
        command_id=command.id,
        task_id=task.id,
        allowed_paths=["src/task.py"],
        instruction="write task",
        phase="focused_file_generation",
    )
    assert agent.call_count == 1
    task_after = result.tasks[0]
    assert task_after.status == "rework_required"
    assert task_after.recovery_reason == "focused_provider_timeout"
    events = [e.type for e in result.events]
    assert "focused_provider_retry_scheduled" not in events


@pytest.mark.asyncio
async def test_mission_budget_exhausted_is_not_retried(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_focused_provider_retry_limit=1,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = BudgetErrorAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["src/task.py"],
        status="ready",
    )
    command = SupervisorCommand(
        id="cmd-budget",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    result = await service._run_focused_agent_step(
        command_id=command.id,
        task_id=task.id,
        allowed_paths=["src/task.py"],
        instruction="write task",
        phase="focused_file_generation",
    )
    task_after = result.tasks[0]
    assert task_after.status == "rework_required"
    assert task_after.recovery_reason == "mission_budget_exhausted"
    events = [e.type for e in result.events]
    assert "focused_provider_retry_scheduled" not in events


@pytest.mark.asyncio
async def test_route_unavailable_is_not_retried(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_focused_provider_retry_limit=1,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = RouteUnavailableAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["src/task.py"],
        status="ready",
    )
    command = SupervisorCommand(
        id="cmd-route",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    result = await service._run_focused_agent_step(
        command_id=command.id,
        task_id=task.id,
        allowed_paths=["src/task.py"],
        instruction="write task",
        phase="focused_file_generation",
    )
    task_after = result.tasks[0]
    assert task_after.status == "rework_required"
    assert task_after.recovery_reason == "focused_route_unavailable"
    events = [e.type for e in result.events]
    assert "focused_provider_retry_scheduled" not in events


@pytest.mark.asyncio
async def test_programming_error_is_not_retried_and_is_focused_step_error(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_focused_provider_retry_limit=1,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = ProgrammingErrorAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["src/task.py"],
        status="ready",
    )
    command = SupervisorCommand(
        id="cmd-prog",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    result = await service._run_focused_agent_step(
        command_id=command.id,
        task_id=task.id,
        allowed_paths=["src/task.py"],
        instruction="write task",
        phase="focused_file_generation",
    )
    task_after = result.tasks[0]
    assert task_after.status == "rework_required"
    assert task_after.recovery_reason == "focused_step_error"
    events = [e.type for e in result.events]
    assert "focused_provider_retry_scheduled" not in events
