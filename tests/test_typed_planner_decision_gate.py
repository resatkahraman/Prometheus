from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoLLM:
    async def run(self, request):
        raise AssertionError("LLM planner must not run")


@pytest.mark.asyncio
async def test_web_uncertainty_decision_then_ready(
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text(
        "def topla(a,b): return a+b\n",
        encoding="utf-8",
    )
    component = tmp_path / "src" / "components"
    component.mkdir(parents=True)
    (component / "Button.tsx").write_text(
        "export function Button(){return <button/>}\n",
        encoding="utf-8",
    )

    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoLLM(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    command = await service.create(
        goal=(
            "Python ve React için test altyapısı planla. "
            "Projenin web uygulaması olup olmadığı belirsizse önce "
            "bana sor. Karar vermeden framework ekleme."
        ),
        autonomy_mode="locked",
    )
    assert command.status == "waiting_decision"
    assert len(command.decisions) == 1

    command = await service.answer_decision(
        command_id=command.id,
        decision_id="DEC-001",
        answer=(
            "Şimdilik tam web uygulamasına dönüştürme. "
            "Python ve React için ayrı test altyapıları kur."
        ),
        replan_when_complete=True,
    )

    assert command.status == "ready"
    assert not any(
        decision.status == "pending"
        for decision in command.decisions
    )
    assert command.tasks[0].status == "ready"
    assert command.tasks[1].status == "ready"
