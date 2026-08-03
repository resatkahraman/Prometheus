from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoPlannerLLM:
    async def run(self, request):
        raise AssertionError("Planner LLM should not be called")


@pytest.mark.asyncio
async def test_pending_web_decision_blocks_tasks(tmp_path: Path):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoPlannerLLM(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = await service.create(
        goal=(
            "Python test altyapısını planla. Projenin web uygulaması "
            "olup olmadığı belirsizse önce bana sor."
        ),
        autonomy_mode="locked",
    )
    assert command.status == "waiting_decision"
    assert all(task.status == "blocked" for task in command.tasks)
