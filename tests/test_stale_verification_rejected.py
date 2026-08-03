from app.supervisor.models import (
    SupervisorApprovalRecord,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService


def test_verification_before_latest_write_is_not_current():
    task = SupervisorTask(
        id="TASK-001",
        title="test",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["score.py"],
        approval_history=[
            SupervisorApprovalRecord(
                version=1,
                approval_id="test",
                state="applied",
                phase="worker",
                tool="safe_terminal",
                success=True,
                result={
                    "command": ["python", "-m", "pytest", "-q"],
                    "exit_code": 0,
                    "success": True,
                },
            ),
            SupervisorApprovalRecord(
                version=2,
                approval_id="write",
                state="applied",
                phase="worker",
                tool="workspace_write",
                success=True,
                result={"changed": True, "path": "score.py"},
            ),
        ],
    )

    service = object.__new__(SupervisorService)
    assert service._latest_successful_verification(task) is None
