from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse, AgentStep
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoAgent:
    pass


@pytest.mark.asyncio
async def test_applied_write_plus_model_limit_becomes_continuation(
    tmp_path: Path,
):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_auto_review=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",title="Test",priority="zorunlu",
        assigned_agent="qa",evidence=[],acceptance_criteria=["x"],
        dependencies=[],dependency_reason="yok",parallelizable="evet",
        verification="pytest",user_approval="gerekli",exact_files=[],
        status="running",
    )
    command = SupervisorCommand(
        id="cmd",goal="test",status="running",plan_text="",tasks=[task]
    )
    response = AgentResponse(
        answer="QA adım/model sınırına ulaştı.",
        agent_id="qa",agent_name="QA",status="max_steps",
        steps_used=2,model_calls_used=2,tools_used=["workspace_write"],
        trace=[AgentStep(
            step=1,selected_route="github",provider="github",model="x",
            action="tool",tool="workspace_write",arguments={},
            tool_result={"path":"tests/test_app.py","changed":True},
            latency_ms=1,
        )],
    )
    await service._handle_worker_response(
        command=command,task=task,response=response
    )
    assert task.status == "rework_required"
    assert task.approval_state == "applied"
    assert "Devam Et" in (task.last_approval_message or "")
