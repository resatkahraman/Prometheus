from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import (
    SupervisorApprovalRecord,
    SupervisorCommand,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class AgentMustNotRun:
    async def run(self, request):
        raise AssertionError("Kanıt yeterli; model çağrılmamalı")


def make_task() -> SupervisorTask:
    return SupervisorTask(
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
        exact_files=["score.py", "tests/test_score.py"],
        status="rework_required",
        attempts=1,
        continuation_resumes=1,
        recovery_reason="model_limit_with_ledger",
        approval_history=[
            SupervisorApprovalRecord(
                version=1,
                approval_id="write-1",
                state="applied",
                phase="worker",
                tool="workspace_write",
                success=True,
                result={"changed": True, "path": "score.py"},
            ),
            SupervisorApprovalRecord(
                version=2,
                approval_id="write-2",
                state="applied",
                phase="worker",
                tool="workspace_write",
                success=True,
                result={"changed": True, "path": "tests/test_score.py"},
            ),
            SupervisorApprovalRecord(
                version=3,
                approval_id="test-1",
                state="applied",
                phase="worker",
                tool="safe_terminal",
                success=True,
                result={
                    "command": ["python", "-m", "pytest", "-q"],
                    "exit_code": 0,
                    "success": True,
                    "stdout": "6 passed",
                },
            ),
        ],
    )


@pytest.mark.asyncio
async def test_rework_completes_locally_when_evidence_is_sufficient(
    tmp_path: Path,
):
    (tmp_path / "score.py").write_text(
        "def calculate_score(a,b,c): return a*b+c\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_score.py").write_text(
        "def test_score(): assert True\n",
        encoding="utf-8",
    )

    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=AgentMustNotRun(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="cmd",
        goal="score",
        status="ready",
        plan_text="",
        tasks=[make_task()],
    )
    await service.store.put(command)

    result = await service.run_task(
        command_id=command.id,
        task_id="TASK-001",
    )

    assert result.tasks[0].status == "completed"
    assert result.tasks[0].review_answer.startswith("KABUL")
    assert any(
        event.type == "task_evidence_reconciled"
        for event in result.events
    )
