from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse
from app.supervisor.models import (
    SupervisorApprovalRecord,
    SupervisorCommand,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoAgent:
    pass


@pytest.mark.asyncio
async def test_model_limit_with_applied_ledger_is_not_failed(
    tmp_path: Path,
):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="score",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["pytest"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["score.py"],
        status="running",
        approval_history=[
            SupervisorApprovalRecord(
                version=1,
                approval_id="write",
                state="applied",
                phase="worker",
                tool="workspace_write",
                success=True,
                result={"changed": True, "path": "score.py"},
            )
        ],
    )
    command = SupervisorCommand(
        id="cmd",
        goal="score",
        status="running",
        plan_text="",
        tasks=[task],
    )
    response = AgentResponse(
        answer="Backend Engineer adım/model sınırına ulaştı.",
        agent_id="backend",
        agent_name="Backend",
        status="max_steps",
        steps_used=24,
        model_calls_used=20,
        tools_used=[],
        trace=[],
    )

    await service._handle_worker_response(
        command=command,
        task=task,
        response=response,
    )

    assert task.status == "rework_required"
    assert task.recovery_reason == "model_limit_with_ledger"
