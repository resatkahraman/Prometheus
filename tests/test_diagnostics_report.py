from app.supervisor.diagnostics import build_command_diagnostics
from app.supervisor.models import SupervisorCommand, SupervisorTask


def test_diagnostics_contains_copyable_errors_and_masks_secrets():
    task = SupervisorTask(
        id="TASK-001",
        title="Test",
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
        status="failed",
        last_answer="api_key=very-secret-value",
    )
    command = SupervisorCommand(
        id="cmd",
        goal="test",
        status="failed",
        plan_text="plan",
        tasks=[task],
        failure_reason="model limit reached",
    )
    report = build_command_diagnostics(command)
    assert "PROMETHEUS TANILAMA RAPORU" in report
    assert "model limit reached" in report
    assert "very-secret-value" not in report
    assert "api_key=***" in report
