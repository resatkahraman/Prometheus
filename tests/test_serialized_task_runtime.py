import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


def make_task(task_id: str, agent: str = "backend") -> SupervisorTask:
    return SupervisorTask(
        id=task_id,
        title=task_id,
        priority="zorunlu",
        assigned_agent=agent,
        evidence=[],
        acceptance_criteria=["kanıt"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=[],
        status="ready",
    )


class ControlledCompletedAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, request):
        self.started.set()
        await self.release.wait()
        return AgentResponse(
            answer="tamam",
            agent_id=request.agent_id or "worker",
            agent_name="Agent",
            status="completed",
            steps_used=1,
            model_calls_used=1,
            tools_used=[],
            trace=[],
        )


@pytest.mark.asyncio
async def test_second_task_cannot_start_while_first_is_active(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_operation_heartbeat_seconds=0.05,
        supervisor_stale_operation_seconds=1.0,
        supervisor_task_agent_timeout_seconds=10.0,
        supervisor_auto_review=False,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = ControlledCompletedAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd-serial",
        goal="test",
        status="ready",
        plan_text="",
        tasks=[
            make_task("TASK-001"),
            make_task("TASK-002", "frontend"),
        ],
    )
    await service.store.put(command)

    started = await service.run_task(
        command_id=command.id,
        task_id="TASK-001",
        background=True,
    )
    initial_heartbeat = started.last_heartbeat_at

    background_job = service._background_jobs.get(
        (command.id, "task:TASK-001")
    )
    assert background_job is not None

    try:
        await asyncio.wait_for(
            agent.started.wait(),
            timeout=1.0,
        )

        with pytest.raises(
            ValueError,
            match="aynı anda yalnızca bir görev",
        ):
            await service.run_task(
                command_id=command.id,
                task_id="TASK-002",
                background=True,
            )

        deadline = asyncio.get_running_loop().time() + 1.0

        while True:
            persisted = await service.store.get(command.id)

            if (
                persisted.last_heartbeat_at is not None
                and persisted.last_heartbeat_at != initial_heartbeat
            ):
                break

            if asyncio.get_running_loop().time() >= deadline:
                pytest.fail(
                    "Arka plan görevi heartbeat üretmedi."
                )

            await asyncio.sleep(0.01)

        current = await service.get(command.id)

        assert current.status == "running"
        assert current.active_operation == "task:TASK-001"
        assert current.tasks[0].status == "running"
        assert current.tasks[1].status == "ready"
        assert current.last_heartbeat_at != initial_heartbeat
    finally:
        agent.release.set()
        await asyncio.wait_for(
            background_job,
            timeout=1.0,
        )


@pytest.mark.asyncio
async def test_task_watchdog_recovers_only_task(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_stale_operation_seconds=1.0,
    )
    settings.supervisor_stale_operation_seconds = 0.01

    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=ControlledCompletedAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    task = make_task("TASK-001")
    task.status = "running"

    command = SupervisorCommand(
        id="cmd-watchdog",
        goal="test",
        status="running",
        plan_text="",
        tasks=[task],
        active_operation="task:TASK-001",
        operation_phase="agent_work",
        operation_message="test",
        operation_started_at="2020-01-01T00:00:00+00:00",
        last_heartbeat_at="2020-01-01T00:00:00+00:00",
    )
    await service.store.put(command)

    result = await service.get(command.id)

    assert result.status == "ready"
    assert result.failure_reason is None
    assert result.tasks[0].status == "rework_required"
    assert any(
        event.type == "task_watchdog_recovered"
        for event in result.events
    )
