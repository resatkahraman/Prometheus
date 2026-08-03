from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class HangingAgent:
    async def run(self, request):
        raise AssertionError(
            "Typed Planning Compiler must bypass the hanging agent"
        )


@pytest.mark.asyncio
async def test_hanging_provider_cannot_block_planning(tmp_path: Path):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=HangingAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = await service.create(goal="Python testlerini planla.")
    assert command.status == "ready"
    assert command.failure_reason is None
