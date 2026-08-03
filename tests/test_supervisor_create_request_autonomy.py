from app.core.schemas import SupervisorCreateRequest


def test_supervisor_create_request_accepts_task_autonomy():
    request = SupervisorCreateRequest(
        goal="Bir görev oluştur",
        autonomy_mode="task",
        background=True,
    )
    assert request.autonomy_mode == "task"


def test_supervisor_create_request_defaults_to_task_autonomy():
    request = SupervisorCreateRequest(goal="Bir görev oluştur")
    assert request.autonomy_mode == "task"
