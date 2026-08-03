from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class PlannerMustNotCallLLM:
    async def run(self, request):
        raise AssertionError(
            "Supervisor planning must not call AgentEngine"
        )


@pytest.mark.asyncio
async def test_supervisor_planning_uses_zero_model_calls(
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text(
        "def topla(a,b): return a+b\n",
        encoding="utf-8",
    )
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=PlannerMustNotCallLLM(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    command = await service.create(
        goal="Python fonksiyonu için test altyapısı planla.",
    )

    assert command.status == "ready"
    assert command.planning_agent_response is not None
    assert command.planning_agent_response.model_calls_used == 0
    assert command.planning_agent_response.final_route == (
        "deterministic_kernel"
    )
    assert any(
        event.type == "planning_kernel_completed"
        for event in command.events
    )
