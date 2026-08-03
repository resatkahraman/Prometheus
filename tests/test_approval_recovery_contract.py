from app.supervisor.service import SupervisorService


def test_supervisor_has_continuation_recovery():
    assert hasattr(
        SupervisorService,
        "_recover_continuation_failure",
    )
