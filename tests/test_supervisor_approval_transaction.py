import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse, ApprovalInfo
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class ApprovalAgent:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def approve(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.04)
        return self.response

    async def reject(self, **kwargs):
        return self.response


async def service_with_task(tmp_path: Path, response: AgentResponse):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_auto_review=False,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = ApprovalAgent(response)
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="Test",
        priority="zorunlu",
        assigned_agent="qa",
        evidence=[{"type":"file","value":"app.py"}],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="pytest",
        user_approval="gerekli",
        exact_files=[],
        status="awaiting_approval",
        agent_session_id="session",
        approval_id="approval-old",
        approval_phase="worker",
        approval_version=1,
        approval_state="pending",
        approval_tool="workspace_write",
        approval_description="write",
        approval_preview={"diff":"+test"},
    )
    command = SupervisorCommand(
        id="command",
        goal="test",
        status="awaiting_approval",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)
    return service, agent


@pytest.mark.asyncio
async def test_double_supervisor_approval_runs_agent_once(tmp_path: Path):
    response = AgentResponse(
        answer="Tamamlandı.",
        agent_id="qa",
        agent_name="QA",
        status="completed",
        steps_used=1,
        model_calls_used=1,
        tools_used=["workspace_write"],
        trace=[],
    )
    service, agent = await service_with_task(tmp_path, response)
    first, second = await asyncio.gather(
        service.approve(
            command_id="command",
            task_id="TASK-001",
            expected_approval_id="approval-old",
            expected_approval_version=1,
            background=True,
        ),
        service.approve(
            command_id="command",
            task_id="TASK-001",
            expected_approval_id="approval-old",
            expected_approval_version=1,
            background=True,
        ),
    )
    assert first.tasks[0].approval_state == "processing"
    assert second.tasks[0].approval_state == "processing"
    for _ in range(50):
        await asyncio.sleep(0.01)
        current = await service.get("command")
        if current.tasks[0].status == "completed":
            break
    assert agent.calls == 1
    assert current.tasks[0].status == "completed"
    assert current.tasks[0].last_consumed_approval_id == "approval-old"


@pytest.mark.asyncio
async def test_next_approval_replaces_old_card_without_mismatch(
    tmp_path: Path,
):
    response = AgentResponse(
        answer="Yeni onay.",
        agent_id="qa",
        agent_name="QA",
        status="awaiting_approval",
        steps_used=2,
        model_calls_used=2,
        tools_used=["workspace_write","safe_terminal"],
        session_id="session",
        pending_approval=ApprovalInfo(
            id="approval-new",
            tool_name="safe_terminal",
            arguments={"preset":"pytest"},
            description="test",
            preview={"command":"python -m pytest -q"},
            created_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-01-01T01:00:00+00:00",
        ),
        trace=[],
    )
    service, agent = await service_with_task(tmp_path, response)
    await service.approve(
        command_id="command",
        task_id="TASK-001",
        expected_approval_id="approval-old",
        expected_approval_version=1,
        background=True,
    )
    for _ in range(50):
        await asyncio.sleep(0.01)
        current = await service.get("command")
        if current.tasks[0].approval_id == "approval-new":
            break
    assert current.tasks[0].status == "awaiting_approval"
    assert current.tasks[0].approval_version == 2
    assert current.tasks[0].approval_id == "approval-new"
    duplicate = await service.approve(
        command_id="command",
        task_id="TASK-001",
        expected_approval_id="approval-old",
        expected_approval_version=1,
        background=True,
    )
    assert duplicate.tasks[0].approval_id == "approval-new"
    assert agent.calls == 1
