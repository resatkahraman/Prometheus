from pathlib import Path

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoAgent:
    pass


def test_focused_timeout_is_a_state_token_block(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-002",
        title="frontend",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=["src/components/X.tsx"],
    )
    command = SupervisorCommand(
        id="cmd",
        goal="x",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    service._mark_task_blocked(
        task=task,
        recovery_reason="focused_provider_timeout",
        message="timeout",
    )
    assert task.blocked_state_token == service._task_state_token(task)
