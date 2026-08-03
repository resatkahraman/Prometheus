from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import SupervisorCommand, SupervisorFailureRecord, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry
from app.tools.terminal import TERMINAL_RUNTIME_REVISION


class NoModel:
    async def run(self, request):
        raise AssertionError("model must not run")


def service(tmp_path: Path) -> SupervisorService:
    settings = Settings(workspace_root=tmp_path, supervisor_approval_background=False)
    tools = build_default_tool_registry(settings=settings)
    return SupervisorService(
        settings=settings,
        agent=NoModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )


def task() -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="frontend",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[{"type": "user_request", "value": "x"}],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=["src/X.tsx", "src/X.test.tsx"],
        status="rework_required",
        recovery_reason="repeated_failure_blocked",
        terminal_runtime_revision="terminal-env-v3",
        failure_counts={"old": 4},
        failure_history=[
            SupervisorFailureRecord(
                signature="old",
                kind="npm_install_failed",
                summary="node not in child PATH",
                count=4,
            )
        ],
    )


def test_runtime_upgrade_clears_old_toolchain_block(tmp_path: Path):
    svc = service(tmp_path)
    t = task()
    command = SupervisorCommand(id="cmd", goal="x", status="ready", plan_text="", tasks=[t])

    changed = svc._reconcile_terminal_runtime_revision(command=command, task=t)

    assert changed is True
    assert t.terminal_runtime_revision == TERMINAL_RUNTIME_REVISION
    assert t.failure_counts == {}
    assert t.failure_history == []
    assert t.recovery_reason is None
    assert command.events[-1].type == "terminal_runtime_revision_advanced"


@pytest.mark.asyncio
async def test_resume_without_state_change_is_noop(tmp_path: Path):
    svc = service(tmp_path)
    t = task()
    t.terminal_runtime_revision = TERMINAL_RUNTIME_REVISION
    command = SupervisorCommand(id="cmd", goal="x", status="ready", plan_text="", tasks=[t])
    t.blocked_state_token = svc._task_state_token(t)
    await svc.store.put(command)

    result = await svc.run_task(command_id="cmd", task_id="TASK-001", background=False)
    repeated = await svc.run_task(
        command_id="cmd",
        task_id="TASK-001",
        background=False,
    )

    assert result.tasks[0].attempts == 0
    assert result.tasks[0].status == "rework_required"
    assert result.events[-1].type == "resume_ignored_no_state_change"
    assert len(
        [
            event
            for event in repeated.events
            if event.type == "resume_ignored_no_state_change"
        ]
    ) == 1


@pytest.mark.asyncio
async def test_exhausted_output_quality_does_not_restart_model(tmp_path: Path):
    svc = service(tmp_path)
    t = task()
    t.terminal_runtime_revision = TERMINAL_RUNTIME_REVISION
    t.recovery_reason = "focused_output_quality"
    t.failure_counts = {"focused_output_quality": 2}
    t.blocked_reason = "Üretilen dosya iki kalite denemesinde de reddedildi."
    t.blocked_state_token = svc._task_state_token(t)
    command = SupervisorCommand(id="quality-cmd", goal="x", status="ready", plan_text="", tasks=[t])
    await svc.store.put(command)

    result = await svc.run_task(
        command_id="quality-cmd",
        task_id="TASK-001",
        background=False,
    )

    assert result.tasks[0].attempts == 0
    assert result.tasks[0].recovery_reason == "focused_output_quality"
    assert result.events[-1].type == "resume_ignored_no_state_change"
