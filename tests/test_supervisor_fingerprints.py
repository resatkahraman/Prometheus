from app.supervisor.models import (
    SupervisorApprovalRecord,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.tools.fingerprint import tool_fingerprint


def test_supervisor_collects_only_applied_fingerprints():
    applied_args = {"path": "score.py", "content": "x = 1\n"}
    task = SupervisorTask(
        id="TASK-001",
        title="score",
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
                approval_id="a",
                state="applied",
                phase="worker",
                tool="workspace_write",
                arguments=applied_args,
                fingerprint=tool_fingerprint(
                    "workspace_write",
                    applied_args,
                ),
                success=True,
            ),
            SupervisorApprovalRecord(
                version=2,
                approval_id="b",
                state="rejected",
                phase="worker",
                tool="workspace_write",
                arguments={"path": "score.py", "content": "x = 2\n"},
            ),
        ],
    )

    values = SupervisorService._applied_tool_fingerprints(task)
    assert values == [
        tool_fingerprint("workspace_write", applied_args)
    ]
