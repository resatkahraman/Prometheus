import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class EmptyAgent:
    async def run(self, request):
        raise AssertionError("not used")


@pytest.mark.asyncio
async def test_unhandled_background_error_is_written_to_command(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=EmptyAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd-crash",
        goal="test",
        status="planning",
        plan_text="",
        tasks=[],
        active_operation="planning",
        operation_phase="queued",
        operation_message="test",
    )
    await service.store.put(command)

    async def crash():
        raise RuntimeError("boom")

    service._spawn(
        crash(),
        command_id=command.id,
        operation="test-operation",
    )

    for _ in range(30):
        await asyncio.sleep(0.01)
        command = await service.get(command.id)
        if command.status == "failed":
            break

    assert command.status == "failed"
    assert "boom" in (command.failure_reason or "")
    assert any(
        event.type == "background_crashed"
        for event in command.events
    )
