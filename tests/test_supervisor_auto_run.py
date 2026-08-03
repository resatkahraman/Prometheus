from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.agents.registry import build_default_agent_registry
from app.command_ui import COMMAND_UI
from app.core.config import Settings
from app.core.schemas import AgentResponse
from app.planning.models import PlanEvidence, PlanningDocument, PlanTask
from app.supervisor.models import SupervisorCommand
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class CompletedAgent:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, request):
        self.calls.append(request)
        return AgentResponse(
            answer="Görev tamamlandı.",
            agent_id=request.agent_id or "worker",
            agent_name=request.agent_id or "worker",
            status="completed",
            steps_used=1,
            model_calls_used=1,
            tools_used=[],
            trace=[],
        )


def make_service(tmp_path: Path) -> tuple[SupervisorService, CompletedAgent]:
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_trusted_autonomy_enabled=True,
        supervisor_persistence_enabled=False,
        supervisor_auto_review=False,
        supervisor_auto_run_max_tasks=10,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = CompletedAgent()
    return (
        SupervisorService(
            settings=settings,
            agent=agent,
            agents=build_default_agent_registry(tools.names()),
            tools=tools,
        ),
        agent,
    )


def planning_result() -> tuple[
    AgentResponse,
    PlanningDocument,
    list[list[str]],
]:
    tasks = [
        PlanTask(
            id="TASK-001",
            title="Birinci görevi tamamla",
            priority="zorunlu",
            assigned_agent="worker",
            evidence=[
                PlanEvidence(type="user_request", value="Otomatik çalıştır")
            ],
            acceptance_criteria=["Görev tamamlanmış durumda olmalı."],
            dependencies=[],
            dependency_reason="yok",
            parallelizable="evet",
            verification="yerel inceleme",
            user_approval="gerekmez",
            exact_files=[],
        ),
        PlanTask(
            id="TASK-002",
            title="İkinci görevi tamamla",
            priority="zorunlu",
            assigned_agent="qa",
            evidence=[
                PlanEvidence(type="user_request", value="Otomatik çalıştır")
            ],
            acceptance_criteria=["Görev tamamlanmış durumda olmalı."],
            dependencies=[],
            dependency_reason="yok",
            parallelizable="evet",
            verification="yerel inceleme",
            user_approval="gerekmez",
            exact_files=[],
        ),
    ]
    response = AgentResponse(
        answer="İki görevli plan.",
        agent_id="planner",
        agent_name="Planner",
        status="completed",
        steps_used=1,
        model_calls_used=0,
        tools_used=[],
        trace=[],
    )
    return (
        response,
        PlanningDocument(tasks=tasks),
        [["TASK-001", "TASK-002"]],
    )


@pytest.mark.asyncio
async def test_auto_start_runs_ready_tasks_until_mission_completes(
    tmp_path: Path,
):
    service, agent = make_service(tmp_path)
    result = planning_result()

    async def fake_plan(**_kwargs):
        return result

    service._plan = fake_plan
    command = await service.create(
        goal="İki görevi otomatik tamamla",
        auto_start=True,
        autonomy_mode="trusted",
    )

    assert command.auto_run is True
    assert command.status == "completed"
    assert [task.status for task in command.tasks] == [
        "completed",
        "completed",
    ]
    assert [call.agent_id for call in agent.calls] == ["worker", "qa"]


@pytest.mark.asyncio
async def test_approval_completion_resumes_an_auto_run_mission(
    tmp_path: Path,
):
    service, _agent = make_service(tmp_path)
    command = SupervisorCommand(
        id="cmd-auto-resume",
        goal="Devam et",
        status="ready",
        autonomy_mode="trusted",
        auto_run=True,
        plan_text="",
        tasks=[],
    )
    service._complete_approval_transaction = AsyncMock(
        return_value=command
    )
    service.advance = AsyncMock(return_value=command)

    result = await service._complete_approval_transaction_and_resume(
        command_id=command.id,
        task_id="TASK-001",
        session_id="session",
        approval_id="approval",
        approval_version=1,
        phase="worker",
    )

    assert result is command
    service.advance.assert_awaited_once_with(
        command_id=command.id,
        max_tasks=service.settings.supervisor_auto_run_max_tasks,
    )


def test_command_center_starts_task_scoped_missions_automatically():
    assert '<option value="task" selected>' in COMMAND_UI
    assert '<option value="trusted">' in COMMAND_UI
    assert "auto_start:true" in COMMAND_UI
