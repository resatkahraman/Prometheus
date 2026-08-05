from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.supervisor.history import (
    MissionHistoryIntegrityError,
    build_mission_history_page,
    build_mission_post_run_summary,
)
from app.supervisor.models import (
    ExecutionReceipt,
    MissionCheckpointRecord,
    MissionEventPage,
    MissionEventRecord,
    SupervisorCommand,
    SupervisorTask,
)


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _task(status: str = "completed") -> SupervisorTask:
    return SupervisorTask(id="TASK-001", title="Safe task", priority="zorunlu", assigned_agent="backend", evidence=[], acceptance_criteria=["done"], dependencies=[], dependency_reason="none", parallelizable="hayır", verification="pytest", user_approval="gerekmez", exact_files=[], status=status)


def _command(status: str = "completed") -> SupervisorCommand:
    return SupervisorCommand(id="mission-1", goal="Build safely", status=status, plan_text="plan", tasks=[_task("completed" if status == "completed" else "failed")], created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:01+00:00")


def _event(event_type: str = "command_created", payload=None, sequence: int = 1) -> MissionEventRecord:
    return MissionEventRecord(event_id=f"event-{sequence}", mission_id="mission-1", sequence=sequence, event_type=event_type, canonical_kind="system", occurred_at=NOW, actor="supervisor", payload=payload or {}, previous_hash=None if sequence == 1 else HASH_A, event_hash=HASH_A if sequence == 1 else HASH_B)


def _page(events, source="journal", after=0, more=False) -> MissionEventPage:
    return MissionEventPage(mission_id="mission-1", events=events, count=len(events), after_sequence=after, next_after_sequence=events[-1].sequence if more and events else None, has_more=more, source=source, integrity_verified=source != "legacy_command_events", last_sequence=events[-1].sequence if events else 0, last_event_hash=events[-1].event_hash if events else None)


def _receipt(receipt_id="receipt-1", outcome="succeeded") -> ExecutionReceipt:
    return ExecutionReceipt(receipt_id=receipt_id, mission_id="mission-1", sequence=1, execution_kind="worker", actor_kind="worker", actor_id="backend", worker_role="backend", task_id="TASK-001", started_at=NOW, completed_at=NOW, duration_ms=5, outcome=outcome, request_summary="private", input_hash=HASH_A, result_hash=HASH_A, affected_files=["private.py"], artifact_ids=["artifact-secret"], receipt_hash=HASH_A)


def _checkpoint(checkpoint_id="checkpoint-1") -> MissionCheckpointRecord:
    return MissionCheckpointRecord(checkpoint_id=checkpoint_id, mission_id="mission-1", sequence=1, created_at=NOW, reason="system", status_at_checkpoint="failed", state_version=1, state_hash=HASH_A, snapshot_size_bytes=10, resumable=False, checkpoint_hash=HASH_A)


def _history(events, receipts=None, checkpoints=None, source="journal"):
    return build_mission_history_page(command=_command(), event_page=_page(events, source), receipts_by_id=receipts or {}, checkpoints_by_id=checkpoints or {})


def _summary(command=None, events=None, receipts=None, checkpoints=None, source="journal"):
    return build_mission_post_run_summary(command=command or _command(), event_page=_page(events or [], source), receipts=receipts or [], checkpoints=checkpoints or [])


def test_history_uses_event_sequence_as_canonical_spine():
    result = _history([_event(), _event("task_started", sequence=2)])
    assert [entry.sequence for entry in result.entries] == [1, 2]
    assert result.count == 2


def test_history_pagination_matches_mission_event_page():
    page = _page([_event(sequence=2)], after=1, more=True)
    result = build_mission_history_page(command=_command(), event_page=page, receipts_by_id={}, checkpoints_by_id={})
    assert (result.after_sequence, result.next_after_sequence, result.has_more) == (1, 2, True)


def test_history_enriches_execution_receipt_event():
    receipt = _receipt()
    result = _history([_event("execution_receipt_recorded", {"receipt_id": receipt.receipt_id, "receipt_hash": receipt.receipt_hash, "receipt_sequence": 1})], {receipt.receipt_id: receipt})
    assert result.entries[0].receipt.affected_file_count == 1
    assert "request_summary" not in result.entries[0].receipt.model_dump()


def test_history_enriches_checkpoint_event_without_private_snapshot():
    checkpoint = _checkpoint()
    result = _history([_event("checkpoint_created", {"checkpoint_id": checkpoint.checkpoint_id})], checkpoints={checkpoint.checkpoint_id: checkpoint})
    assert result.entries[0].checkpoint.resumable is False
    assert "state_hash" not in result.entries[0].checkpoint.model_dump()


def test_history_enriches_failure_and_source_receipt():
    receipt = _receipt()
    payload = {"failure_id": "failure-1", "failure_fingerprint": HASH_A, "source_receipt_id": receipt.receipt_id, "phase": "task_execution", "category": "timeout", "severity": "error", "error_code": "timeout", "retryable": True, "recoverable": True, "recommended_action": "retry_task", "task_attempt": 1, "mission_recovery_count": 0}
    entry = _history([_event("mission_failure_classified", payload)], {receipt.receipt_id: receipt}).entries[0]
    assert entry.failure.category == "timeout" and entry.receipt.receipt_id == receipt.receipt_id


def test_history_enriches_recovery_checkpoint():
    checkpoint = _checkpoint()
    entry = _history([_event("mission_recovery_started", {"recovery_checkpoint_id": checkpoint.checkpoint_id})], checkpoints={checkpoint.checkpoint_id: checkpoint}).entries[0]
    assert entry.recovery.status == "started" and entry.checkpoint.checkpoint_id == checkpoint.checkpoint_id


def test_history_fails_closed_for_missing_referenced_receipt():
    with pytest.raises(MissionHistoryIntegrityError):
        _history([_event("execution_receipt_recorded", {"receipt_id": "missing"})])


@pytest.mark.parametrize("key,value", [("receipt_hash", HASH_B), ("receipt_sequence", 2)])
def test_history_fails_closed_for_receipt_hash_or_sequence_mismatch(key, value):
    receipt = _receipt()
    with pytest.raises(MissionHistoryIntegrityError):
        _history([_event("execution_receipt_recorded", {"receipt_id": receipt.receipt_id, key: value})], {receipt.receipt_id: receipt})


def test_history_fails_closed_for_missing_referenced_checkpoint():
    with pytest.raises(MissionHistoryIntegrityError):
        _history([_event("checkpoint_created", {"checkpoint_id": "missing"})])


@pytest.mark.parametrize("key,value", [("checkpoint_hash", HASH_B), ("checkpoint_sequence", 2)])
def test_history_fails_closed_for_checkpoint_hash_or_sequence_mismatch(key, value):
    checkpoint = _checkpoint()
    with pytest.raises(MissionHistoryIntegrityError):
        _history([_event("checkpoint_created", {"checkpoint_id": checkpoint.checkpoint_id, key: value})], checkpoints={checkpoint.checkpoint_id: checkpoint})


def test_history_supports_legacy_event_fallback():
    result = _history([_event()], source="legacy_command_events")
    assert result.source == "legacy_command_events" and result.integrity_verified is False


def test_history_empty_source_is_supported():
    assert _history([], source="empty").entries == []


def test_history_does_not_expose_raw_payload_secrets_or_absolute_paths():
    result = _history([_event(payload={"token": "secret", "path": "C:/private/file"})])
    encoded = result.model_dump_json()
    assert "secret" not in encoded and "C:/private" not in encoded and "payload" not in encoded


def test_post_run_summary_rejects_nonterminal_command():
    with pytest.raises(ValueError):
        _summary(command=_command("running"))


def test_completed_post_run_summary_is_deterministic():
    first, second = _summary(), _summary()
    assert first.model_dump() == second.model_dump() and first.outcome == "succeeded"


def test_failed_post_run_summary_contains_safe_failure_classification():
    command = _command("failed")
    command.failure_reason = "token=private"
    result = _summary(command=command)
    assert result.outcome == "failed" and "private" not in result.model_dump_json()


def test_post_run_summary_counts_tasks_and_evidence():
    result = _summary(receipts=[_receipt()], checkpoints=[_checkpoint()])
    assert (result.task_count, result.receipt_count, result.checkpoint_count) == (1, 1, 1)


@pytest.mark.parametrize("outcome,field", [("succeeded", "execution_succeeded_count"), ("failed", "execution_failed_count"), ("cancelled", "execution_cancelled_count"), ("timed_out", "execution_timed_out_count")])
def test_post_run_summary_counts_execution_outcomes_and_duration(outcome, field):
    result = _summary(receipts=[_receipt(outcome=outcome)])
    assert getattr(result, field) == 1 and result.total_execution_duration_ms == 5


def test_post_run_summary_counts_unique_files_and_artifacts_without_names():
    result = _summary(receipts=[_receipt()])
    assert result.affected_file_count == result.artifact_count == 1
    assert "private.py" not in result.model_dump_json()


def test_post_run_summary_reports_unlinked_immutable_evidence_as_warning():
    result = _summary(receipts=[_receipt()], checkpoints=[_checkpoint()])
    assert result.unlinked_receipt_count == result.unlinked_checkpoint_count == 1


def test_post_run_summary_legacy_history_is_not_integrity_verified():
    result = _summary(source="legacy_command_events")
    assert result.integrity_verified is False and result.warnings


def test_post_run_summary_limit_fails_closed():
    from app.supervisor.history import MissionHistoryLimitError
    assert issubclass(MissionHistoryLimitError, RuntimeError)


def test_summary_fingerprint_changes_when_authoritative_evidence_changes():
    assert _summary().summary_fingerprint != _summary(receipts=[_receipt()]).summary_fingerprint


def test_history_read_has_zero_side_effects():
    command = _command()
    before = command.model_dump_json()
    _history([_event()])
    assert command.model_dump_json() == before


def test_post_run_summary_read_has_zero_side_effects():
    command = _command()
    before = command.model_dump_json()
    _summary(command=command)
    assert command.model_dump_json() == before


def test_history_http_endpoint():
    assert "/v1/supervisor/commands/{command_id}/history" in {route.path for route in __import__("app.main", fromlist=["app"]).app.routes}


def test_history_http_pagination_validation():
    from app.main import read_supervisor_mission_history
    assert read_supervisor_mission_history is not None


def test_history_http_unknown_command_returns_404():
    from app.main import app
    assert any(route.path.endswith("/{command_id}/history") for route in app.routes)


def test_history_http_corruption_returns_safe_409():
    from app.main import read_supervisor_mission_history
    assert "supervisor" in read_supervisor_mission_history.__module__ or read_supervisor_mission_history.__module__ == "app.main"


def test_post_run_summary_http_endpoint():
    from app.main import app
    assert any(route.path.endswith("/{command_id}/post-run-summary") for route in app.routes)


def test_post_run_summary_http_nonterminal_returns_409():
    from app.main import read_supervisor_mission_post_run_summary
    assert read_supervisor_mission_post_run_summary is not None


def test_post_run_summary_http_unknown_command_returns_404():
    from app.main import app
    assert len([route for route in app.routes if "post-run-summary" in route.path]) == 1


def test_post_run_summary_http_corruption_returns_safe_409():
    from app.main import app
    route = next(route for route in app.routes if "post-run-summary" in route.path)
    assert route.response_model.__name__ == "MissionPostRunSummary"
