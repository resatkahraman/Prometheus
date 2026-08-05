from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.event_journal import canonical_event_kind
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.recovery import FailureSignal, classify_mission_failure
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


def _classify(code: str, **kwargs):
    return classify_mission_failure(
        FailureSignal(
            mission_id="mission-1",
            task_id="TASK-001",
            phase=kwargs.pop("phase", "task_execution"),
            error_code=code,
            safe_message=kwargs.pop("safe_message", "safe failure"),
            **kwargs,
        ),
        mission_recovery_count=0,
    )


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("timeout", "timeout"),
        ("rate_limited", "rate_limited"),
        ("transient_provider", "transient_provider"),
        ("dependency_unavailable", "dependency_unavailable"),
        ("verification_failed", "verification_failed"),
    ],
)
def test_recoverable_taxonomy(code: str, category: str) -> None:
    result = _classify(code)
    assert result.category == category
    assert result.retryable is True
    assert result.recoverable is True
    assert result.recommended_action == "retry_task"


def test_timeout_is_recoverable_retry_task() -> None:
    assert _classify("provider_timeout").category == "timeout"


def test_rate_limit_is_recoverable_retry_task() -> None:
    assert _classify("http_429").category == "rate_limited"


def test_transient_provider_is_recoverable_retry_task() -> None:
    assert _classify("provider_connection_reset").category == "transient_provider"


def test_dependency_unavailable_is_recoverable() -> None:
    assert _classify("route_unavailable").recoverable is True


def test_verification_failure_is_recoverable() -> None:
    assert _classify("unknown", verification_failed=True).category == "verification_failed"


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("budget_exhausted", "policy_blocked"),
        ("approval_rejected", "approval_rejected"),
        ("checkpoint_integrity_error", "integrity_failure"),
        ("cancelled", "cancelled"),
        ("not-a-known-signal", "unknown"),
    ],
)
def test_fail_closed_taxonomy(code: str, category: str) -> None:
    result = _classify(code)
    assert result.category == category
    assert result.recoverable is False


def test_policy_failure_is_not_recoverable() -> None:
    assert _classify("unsafe_operation").recoverable is False


def test_approval_rejection_is_not_recoverable() -> None:
    assert _classify("user_rejected").recommended_action == "request_approval"


def test_integrity_failure_is_critical() -> None:
    result = _classify("hash_mismatch")
    assert result.category == "integrity_failure"
    assert result.severity == "critical"


def test_cancelled_is_not_recoverable() -> None:
    assert _classify("operation_cancelled").recoverable is False


def test_unknown_fails_closed() -> None:
    result = _classify("")
    assert result.category == "unknown"
    assert result.recoverable is False


def test_failure_fingerprint_is_deterministic_but_failure_id_is_unique() -> None:
    first = _classify("timeout", task_attempt=2, source_receipt_id="receipt-1")
    second = _classify("timeout", task_attempt=2, source_receipt_id="receipt-1")
    assert first.failure_fingerprint == second.failure_fingerprint
    assert first.failure_id != second.failure_id


def test_failure_message_redacts_secret_and_absolute_path() -> None:
    result = _classify(
        "timeout",
        safe_message=r"token=secret-value at C:\Users\person\private\file.txt",
    )
    assert "secret-value" not in result.safe_message
    assert "C:\\Users" not in result.safe_message
    assert "[REDACTED]" in result.safe_message


def _task(status: str = "failed") -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="Recover task",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["passes"],
        dependencies=[],
        dependency_reason="none",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekmez",
        exact_files=[],
        status=status,
    )


def _command() -> SupervisorCommand:
    failure = _classify("timeout")
    return SupervisorCommand(
        id="mission-1",
        goal="Recover safely",
        status="failed",
        plan_text="plan",
        tasks=[_task()],
        latest_failure=failure,
        recovery_status="eligible",
    )


def test_old_command_json_parses_with_default_recovery_fields() -> None:
    command = SupervisorCommand.model_validate(
        {
            "id": "old-mission",
            "goal": "old",
            "status": "ready",
            "plan_text": "plan",
            "tasks": [_task(status="ready").model_dump(mode="json")],
        }
    )
    assert command.latest_failure is None
    assert command.recovery_status == "idle"
    assert command.recovery_count == 0


def test_recovery_fields_round_trip_through_command_model() -> None:
    command = _command()
    restored = SupervisorCommand.model_validate_json(command.model_dump_json())
    assert restored.latest_failure == command.latest_failure
    assert restored.recovery_status == "eligible"


def test_recovery_events_use_canonical_recovery_kind() -> None:
    for event_type in (
        "mission_failure_classified",
        "mission_recovery_started",
        "mission_recovery_scheduled",
        "mission_recovery_completed",
        "mission_recovery_failed",
        "mission_recovery_blocked",
    ):
        assert canonical_event_kind(event_type) == "recovery"


class _NoModelAgent:
    async def run(self, _request):
        raise AssertionError("model/provider must not be called")


def _service(tmp_path: Path) -> SupervisorService:
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
        project_memory_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    return SupervisorService(
        settings=settings,
        agent=_NoModelAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )


@pytest.mark.asyncio
async def test_recovery_status_read_has_zero_side_effects(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    await service.store.put(command)
    before = command.model_dump_json()
    status = await service.get_mission_recovery_status(command.id)
    after = (await service.store.get(command.id)).model_dump_json()
    assert status.can_recover is True
    assert before == after
    assert command.events == []


@pytest.mark.asyncio
async def test_recoverable_failure_creates_non_resumable_checkpoint_and_schedules_once(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    command = _command()
    await service.store.put(command)
    spawned: list[str] = []

    def fake_spawn(coroutine, *, command_id: str, operation: str) -> bool:
        coroutine.close()
        spawned.append(f"{command_id}:{operation}")
        return True

    service._spawn = fake_spawn  # type: ignore[method-assign]
    response = await service.recover_mission(
        command.id,
        failure_id=command.latest_failure.failure_id,
        expected_control_version=0,
    )
    persisted = await service.store.get(command.id)
    checkpoint = service._get_mission_checkpoint_store().get_checkpoint(
        mission_id=command.id,
        checkpoint_id=persisted.recovery_checkpoint_id,
    )
    assert response.accepted is True and response.scheduled is True
    assert spawned == ["mission-1:mission_recovery"]
    assert persisted.tasks[0].attempts == 0
    assert persisted.active_checkpoint_id is None
    assert checkpoint is not None and checkpoint.resumable is False
    assert checkpoint.resume_target_status is None


@pytest.mark.asyncio
async def test_duplicate_recovery_request_does_not_spawn_twice(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    await service.store.put(command)
    calls = 0

    def fake_spawn(coroutine, **_kwargs) -> bool:
        nonlocal calls
        coroutine.close()
        calls += 1
        return True

    service._spawn = fake_spawn  # type: ignore[method-assign]
    first = await service.recover_mission(command.id)
    second = await service.recover_mission(command.id)
    assert first.idempotent is False
    assert second.idempotent is True
    assert calls == 1


@pytest.mark.asyncio
async def test_expected_control_version_conflict_blocks_recovery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    await service.store.put(command)
    with pytest.raises(ValueError, match="Control version mismatch"):
        await service.recover_mission(command.id, expected_control_version=99)


@pytest.mark.asyncio
async def test_paused_command_must_use_resume(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.status = "paused"
    command.pause_requested = True
    await service.store.put(command)
    with pytest.raises(ValueError, match="mission_resume_required"):
        await service.recover_mission(command.id)


@pytest.mark.asyncio
async def test_policy_failure_blocks_recovery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.latest_failure = _classify("policy_blocked")
    command.recovery_status = "blocked"
    await service.store.put(command)
    with pytest.raises(ValueError, match="failure_not_recoverable"):
        await service.recover_mission(command.id)


@pytest.mark.asyncio
async def test_terminal_failure_records_one_classification_event(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.latest_failure = None
    command.recovery_status = "idle"
    await service._record_mission_failure(
        command=command,
        phase="task_execution",
        error_code="timeout",
        safe_message="timed out",
        task=command.tasks[0],
        source_receipt_id="receipt-1",
        receipt_outcome="failed",
    )
    assert [event.type for event in command.events] == ["mission_failure_classified"]


@pytest.mark.asyncio
async def test_same_failure_fingerprint_is_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.latest_failure = None
    for _ in range(2):
        await service._record_mission_failure(
            command=command,
            phase="task_execution",
            error_code="timeout",
            safe_message="timed out",
            task=command.tasks[0],
            source_receipt_id="receipt-1",
            receipt_outcome="failed",
        )
    assert sum(event.type == "mission_failure_classified" for event in command.events) == 1


@pytest.mark.asyncio
async def test_concurrent_recovery_requests_schedule_exactly_once(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    await service.store.put(command)
    calls = 0

    def fake_spawn(coroutine, **_kwargs) -> bool:
        nonlocal calls
        coroutine.close()
        calls += 1
        return True

    service._spawn = fake_spawn  # type: ignore[method-assign]
    first, second = await asyncio.gather(
        service.recover_mission(command.id),
        service.recover_mission(command.id),
    )
    assert calls == 1
    assert sorted((first.idempotent, second.idempotent)) == [False, True]


@pytest.mark.asyncio
async def test_active_task_blocks_recovery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.tasks.append(_task(status="running").model_copy(update={"id": "TASK-002"}))
    await service.store.put(command)
    with pytest.raises(ValueError, match="active_task"):
        await service.recover_mission(command.id)


@pytest.mark.asyncio
async def test_integrity_failure_blocks_recovery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.latest_failure = _classify("hash_mismatch")
    command.recovery_status = "blocked"
    await service.store.put(command)
    with pytest.raises(ValueError, match="failure_not_recoverable"):
        await service.recover_mission(command.id)


@pytest.mark.asyncio
async def test_per_failure_limit_blocks_second_accepted_recovery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.recovery_attempts_for_failure = 1
    await service.store.put(command)
    with pytest.raises(ValueError, match="failure_recovery_limit_exhausted"):
        await service.recover_mission(command.id)


@pytest.mark.asyncio
async def test_mission_limit_blocks_fourth_recovery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    command.recovery_count = 3
    await service.store.put(command)
    with pytest.raises(ValueError, match="mission_recovery_limit_exhausted"):
        await service.recover_mission(command.id)


@pytest.mark.asyncio
async def test_successful_retry_marks_recovery_recovered(tmp_path: Path) -> None:
    service = _service(tmp_path)
    command = _command()
    task = command.tasks[0]
    command.recovery_status = "running"
    command.recovery_task_id = task.id
    task.status = "completed"
    await service._finalize_mission_recovery_if_needed(command=command, task=task)
    assert command.recovery_status == "recovered"
    assert command.recovery_completed_at is not None
    assert command.events[-1].type == "mission_recovery_completed"
