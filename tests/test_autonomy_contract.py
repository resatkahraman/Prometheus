from app.supervisor.models import SupervisorCommand, SupervisorTask


def task():
    return SupervisorTask(
        id="TASK-001",
        title="x",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["x"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["x.py"],
    )


def test_task_autonomy_defaults_are_explicit():
    command = SupervisorCommand(
        id="cmd",
        goal="x",
        status="ready",
        autonomy_mode="task",
        plan_text="",
        tasks=[task()],
    )
    assert command.autonomy_mode == "task"
    assert command.tasks[0].autonomy_granted is False
