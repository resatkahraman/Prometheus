from pathlib import Path

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import (
    FOCUSED_GENERATION_REVISION,
    SupervisorService,
)
from app.tools.registry import build_default_tool_registry


class NoModel:
    async def run(self, request):
        raise AssertionError("model should not run")


def test_legacy_protocol_failure_is_reset_once(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="Calculator",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["file exists"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=["src/components/Calculator.tsx"],
        status="rework_required",
        recovery_reason="focused_step_failed",
        last_answer=(
            "Frontend Engineer agent protokolüne uygun JSON üretemedi."
        ),
        blocked_reason="legacy protocol failed",
        local_model_attempts=1,
    )
    command = SupervisorCommand(
        id="cmd",
        goal="calculator",
        status="ready",
        plan_text="",
        tasks=[task],
    )

    assert service._reconcile_focused_generation_revision(
        command=command,
        task=task,
    )
    assert task.focused_generation_revision == (
        FOCUSED_GENERATION_REVISION
    )
    assert task.recovery_reason is None
    assert task.blocked_reason is None
    assert task.local_model_attempts == 0
    assert not service._reconcile_focused_generation_revision(
        command=command,
        task=task,
    )
