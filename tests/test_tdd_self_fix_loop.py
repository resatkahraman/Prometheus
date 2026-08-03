import pytest
from app.supervisor.tdd_self_fix import (
    TDDSelfFixLoop,
    TDDSelfFixMaxRetriesExceeded,
)


def test_tdd_self_fix_loop_records_attempts_and_generates_replan():
    loop = TDDSelfFixLoop(command_id="cmd-123", max_retries=3)

    strategy1 = loop.record_failure_and_generate_replan(
        error_message="AssertionError: expected 5, got 4",
        traceback_snippet="File 'calc.py', line 12, in add",
        timestamp="2026-07-31T14:30:00Z",
    )
    assert loop.current_attempt == 1
    assert "DENEME 1/3" in strategy1
    assert "AssertionError: expected 5, got 4" in strategy1

    strategy2 = loop.record_failure_and_generate_replan(
        error_message="TypeError: unsupported operand type",
        traceback_snippet="File 'calc.py', line 15",
        timestamp="2026-07-31T14:31:00Z",
    )
    assert loop.current_attempt == 2
    assert "DENEME 2/3" in strategy2


def test_tdd_self_fix_loop_raises_when_max_retries_exceeded():
    loop = TDDSelfFixLoop(command_id="cmd-456", max_retries=2)
    loop.record_failure_and_generate_replan("Err1", "Trace1", "10:00")
    loop.record_failure_and_generate_replan("Err2", "Trace2", "10:01")

    with pytest.raises(TDDSelfFixMaxRetriesExceeded):
        loop.record_failure_and_generate_replan("Err3", "Trace3", "10:02")


def test_tdd_self_fix_loop_can_resume_from_persisted_attempt_count():
    loop = TDDSelfFixLoop(
        command_id="cmd-resume",
        max_retries=3,
        current_attempt=2,
    )

    strategy = loop.record_failure_and_generate_replan(
        "AssertionError",
        "tests/test_score.py:12",
        "10:03",
    )

    assert loop.current_attempt == 3
    assert "DENEME 3/3" in strategy
