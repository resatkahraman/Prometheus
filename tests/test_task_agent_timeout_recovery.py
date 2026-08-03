import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class HangingAgent:
    async def run(self, request):
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_initial_agent_timeout_does_not_fail_command(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_operation_heartbeat_seconds=0.05,
        supervisor_task_agent_timeout_seconds=10.0,
        supervisor_cancellation_grace_seconds=0.05,
        supervisor_auto_review=False,
    )
    settings.supervisor_operation_heartbeat_seconds = 0.02
    settings.supervisor_task_agent_timeout_seconds = 0.08
    settings.supervisor_cancellation_grace_seconds = 0.02
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=HangingAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001", title="test", priority="zorunlu",
        assigned_agent="backend", evidence=[],
        acceptance_criteria=["test"], dependencies=[],
        dependency_reason="yok", parallelizable="evet",
        verification="python -m pytest -q", user_approval="gerekli",
        exact_files=[], status="ready",
    )
    command = SupervisorCommand(
        id="cmd-timeout", goal="test", status="ready",
        plan_text="", tasks=[task],
    )
    await service.store.put(command)
    result = await service.run_task(
        command_id=command.id,
        task_id=task.id,
        background=False,
    )
    assert result.status == "ready"
    assert result.failure_reason is None
    assert result.tasks[0].status == "rework_required"
    assert any(e.type == "task_agent_timeout_recovered" for e in result.events)
