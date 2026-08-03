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
async def test_answered_web_decision_is_binding(tmp_path: Path):
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
            "Test altyapısı planla. Web uygulaması olup olmadığı "
            "belirsizse önce bana sor; framework ekleme."
        ),
        autonomy_mode="locked",
    )
    assert command.status == "waiting_decision"

    command = await service.answer_decision(
        command_id=command.id,
        decision_id="DEC-001",
        answer=(
            "Şimdilik tam web uygulamasına dönüştürme. "
            "Bağımsız test altyapısı kur."
        ),
        replan_when_complete=True,
    )
    assert command.status == "ready"
    assert command.decision_history
    assert not any(
        decision.status == "pending"
        for decision in command.decisions
    )
