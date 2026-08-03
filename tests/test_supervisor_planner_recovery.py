from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoPlannerModel:
    async def run(self, request):
        raise AssertionError("No planner model call expected")


@pytest.mark.asyncio
async def test_schema_recovery_is_unnecessary_with_typed_document(
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoPlannerModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = await service.create(goal="Test altyapısı planla.")
    assert command.status == "ready"
    assert command.planning_agent_response.steps_used == 1
    assert command.planning_agent_response.model_calls_used == 0
