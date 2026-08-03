import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoAgent:
    pass


@pytest.mark.asyncio
async def test_heartbeat_timeout_does_not_wait_forever(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_operation_heartbeat_seconds=0.05,
        supervisor_cancellation_grace_seconds=0.05,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    async def stubborn():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.sleep(10)

    from app.supervisor.models import SupervisorCommand
    command = SupervisorCommand(
        id="cmd-heartbeat",
        goal="test",
        status="running",
        plan_text="",
        tasks=[],
    )
    await service.store.put(command)

    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await service._await_with_heartbeat(
            stubborn(),
            command_id=command.id,
            timeout_seconds=0.1,
            heartbeat_message="test",
        )
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.5
