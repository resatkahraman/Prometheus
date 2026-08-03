from pathlib import Path

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import (
    SupervisorApprovalRecord,
    SupervisorCommand,
    SupervisorFailureRecord,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.tools.fingerprint import tool_fingerprint
from app.tools.registry import build_default_tool_registry


class NoModelAgent:
    async def run(self, request):
        raise AssertionError("Environment recovery must not call a model")


def make_task() -> SupervisorTask:
    failed_args = {
        "preset": "npm_test",
        "extra_args": ["--run"],
    }
    install_args = {
        "preset": "install_node_lts",
        "extra_args": [],
    }
    return SupervisorTask(
        id="TASK-002",
        title="Frontend tests",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["npm test başarılı"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=[
            "src/components/ScoreCard.tsx",
            "src/components/ScoreCard.test.tsx",
        ],
        status="rework_required",
        autonomy_granted=True,
        recovery_reason="repeated_failure_blocked",
        blocked_reason="old environment failure",
        verification_failures=5,
        failure_counts={"old": 5},
        failure_history=[
            SupervisorFailureRecord(
                signature="old",
                kind="missing_node_toolchain",
                summary="npm missing",
                count=5,
            )
        ],
        attempted_strategies=["install_node_lts"],
        approval_version=2,
        approval_history=[
            SupervisorApprovalRecord(
                version=1,
                approval_id="failed-test",
                state="applied",
                phase="worker",
                tool="safe_terminal",
                arguments=failed_args,
                fingerprint=tool_fingerprint(
                    "safe_terminal",
                    failed_args,
                ),
                success=False,
                result={
                    "preset": "npm_test",
                    "exit_code": 127,
                    "success": False,
                    "failure_kind": "missing_command",
                    "missing_command": "npm",
                    "stderr": "Komut bulunamadı: npm",
                },
            ),
            SupervisorApprovalRecord(
                version=2,
                approval_id="node-install",
                state="applied",
                phase="worker",
                tool="safe_terminal",
                arguments=install_args,
                fingerprint=tool_fingerprint(
                    "safe_terminal",
                    install_args,
                ),
                success=True,
                result={
                    "preset": "install_node_lts",
                    "exit_code": 0,
                    "success": True,
                    "npm_available_after_install": True,
                },
            ),
        ],
    )


def make_service(tmp_path: Path) -> SupervisorService:
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    return SupervisorService(
        settings=settings,
        agent=NoModelAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )


def test_environment_change_invalidates_old_duplicate_guard(
    tmp_path: Path,
):
    service = make_service(tmp_path)
    task = make_task()
    previous_failure = task.approval_history[0]

    assert (
        service._latest_successful_environment_change_version(task)
        > previous_failure.version
    )


def test_environment_revision_clears_stale_failure_state(
    tmp_path: Path,
):
    service = make_service(tmp_path)
    task = make_task()
    command = SupervisorCommand(
        id="cmd",
        goal="frontend",
        status="ready",
        plan_text="",
        tasks=[task],
    )

    changed = service._reconcile_environment_revision(
        command=command,
        task=task,
    )

    assert changed is True
    assert task.environment_revision == 1
    assert task.last_environment_change_version == 2
    assert task.failure_counts == {}
    assert task.failure_history == []
    assert task.verification_failures == 0
    assert task.blocked_reason is None
    assert task.recovery_reason is None
    assert command.events[-1].type == (
        "environment_revision_advanced"
    )


def test_environment_revision_is_idempotent(tmp_path: Path):
    service = make_service(tmp_path)
    task = make_task()
    command = SupervisorCommand(
        id="cmd",
        goal="frontend",
        status="ready",
        plan_text="",
        tasks=[task],
    )

    assert service._reconcile_environment_revision(
        command=command,
        task=task,
    )
    assert not service._reconcile_environment_revision(
        command=command,
        task=task,
    )
    assert task.environment_revision == 1
