from pathlib import Path

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse, ApprovalInfo
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoAgent:
    pass


def make_task(task_id: str = "TASK-001") -> SupervisorTask:
    return SupervisorTask(
        id=task_id,
        title="Test task",
        priority="zorunlu",
        assigned_agent="qa",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="pytest",
        user_approval="gerekli",
        exact_files=[],
    )


def test_pending_approval_is_saved_in_history(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = make_task()
    command = SupervisorCommand(
        id="cmd",
        goal="test",
        status="running",
        plan_text="",
        tasks=[task],
    )
    response = AgentResponse(
        answer="approval",
        agent_id="qa",
        agent_name="QA",
        status="awaiting_approval",
        steps_used=1,
        model_calls_used=1,
        tools_used=[],
        session_id="session",
        pending_approval=ApprovalInfo(
            id="approval-1",
            tool_name="workspace_write",
            arguments={"path": "tests/test_app.py"},
            description="Dosya yazılacak.",
            preview={"path": "tests/test_app.py"},
            created_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T01:00:00+00:00",
        ),
    )

    service._set_pending_approval(
        command=command,
        task=task,
        response=response,
        phase="worker",
    )

    assert task.approval_history
    record = task.approval_history[0]
    assert record.version == 1
    assert record.state == "pending"
    assert record.tool == "workspace_write"
