from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class AgentMustNotRun:
    async def approve(self, **kwargs):
        raise AssertionError("Out-of-order approval must not reach agent")


def make_task(task_id: str, approval_id: str) -> SupervisorTask:
    return SupervisorTask(
        id=task_id,
        title=task_id,
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
        status="awaiting_approval",
        agent_session_id=f"session-{task_id}",
        approval_id=approval_id,
        approval_phase="worker",
        approval_version=1,
        approval_state="pending",
        approval_tool="workspace_write",
    )


@pytest.mark.asyncio
async def test_only_first_pending_approval_can_run(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=AgentMustNotRun(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd-order",
        goal="test",
        status="awaiting_approval",
        plan_text="",
        tasks=[
            make_task("TASK-001", "approval-1"),
            make_task("TASK-002", "approval-2"),
        ],
    )
    await service.store.put(command)

    with pytest.raises(ValueError, match="Onay sırası"):
        await service.approve(
            command_id=command.id,
            task_id="TASK-002",
            expected_approval_id="approval-2",
            expected_approval_version=1,
        )
