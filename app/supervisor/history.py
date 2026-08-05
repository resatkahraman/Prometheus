from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from typing import Any

from app.supervisor.models import (
    ExecutionReceipt,
    ExecutionReceiptSummary,
    MissionCheckpointRecord,
    MissionEventPage,
    MissionHistoryCheckpointSummary,
    MissionHistoryEntry,
    MissionHistoryFailureSummary,
    MissionHistoryPage,
    MissionHistoryRecoverySummary,
    MissionPostRunSummary,
    MissionTaskPostRunSummary,
    SupervisorCommand,
)


class MissionHistoryError(RuntimeError):
    pass


class MissionHistoryIntegrityError(MissionHistoryError):
    pass


class MissionHistoryLimitError(MissionHistoryError):
    pass


MAX_MISSION_HISTORY_RECORDS = 100_000

_LABELS = {
    "command_created": "Mission created",
    "planning_started": "Planning started",
    "plan_accepted": "Plan accepted",
    "task_started": "Task started",
    "task_completed": "Task completed",
    "task_failed": "Task failed",
    "approval_rejected": "Approval rejected",
    "execution_receipt_recorded": "Execution receipt recorded",
    "checkpoint_created": "Mission checkpoint created",
    "mission_pause_requested": "Mission pause requested",
    "mission_paused": "Mission paused",
    "mission_resume_started": "Mission resume started",
    "mission_resumed": "Mission resumed",
    "mission_failure_classified": "Mission failure classified",
    "mission_recovery_started": "Mission recovery started",
    "mission_recovery_scheduled": "Mission recovery scheduled",
    "mission_recovery_completed": "Mission recovery completed",
    "mission_recovery_blocked": "Mission recovery blocked",
    "mission_recovery_failed": "Mission recovery failed",
    "mission_budget_exhausted": "Mission budget exhausted",
}
_RECOVERY_STATUS = {
    "mission_recovery_started": "started",
    "mission_recovery_scheduled": "scheduled",
    "mission_recovery_completed": "completed",
    "mission_recovery_blocked": "blocked",
    "mission_recovery_failed": "failed",
}


def _scalar(payload: Mapping[str, Any], key: str, expected: type) -> Any | None:
    value = payload.get(key)
    return value if isinstance(value, expected) and not isinstance(value, bool) else None


def _text(payload: Mapping[str, Any], key: str, maximum: int = 160) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:maximum] or None


def _boolean(payload: Mapping[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    return value if isinstance(value, bool) else None


def _receipt_summary(receipt: ExecutionReceipt) -> ExecutionReceiptSummary:
    return ExecutionReceiptSummary(
        receipt_id=receipt.receipt_id,
        mission_id=receipt.mission_id,
        sequence=receipt.sequence,
        execution_kind=receipt.execution_kind,
        actor_id=receipt.actor_id,
        task_id=receipt.task_id,
        outcome=receipt.outcome,
        duration_ms=receipt.duration_ms,
        affected_file_count=len(receipt.affected_files),
        artifact_count=len(receipt.artifact_ids),
        receipt_hash=receipt.receipt_hash,
    )


def _checkpoint_summary(record: MissionCheckpointRecord) -> MissionHistoryCheckpointSummary:
    return MissionHistoryCheckpointSummary(
        checkpoint_id=record.checkpoint_id,
        sequence=record.sequence,
        created_at=record.created_at,
        reason=record.reason,
        status_at_checkpoint=record.status_at_checkpoint,
        resume_target_status=record.resume_target_status,
        current_task_id=record.current_task_id,
        resumable=record.resumable,
        consumed_by_resume=record.consumed_by_resume,
        checkpoint_hash=record.checkpoint_hash,
    )


def _resolve_receipt(event, payload: Mapping[str, Any], receipts: Mapping[str, ExecutionReceipt]) -> ExecutionReceiptSummary | None:
    receipt_id = _text(payload, "receipt_id") or _text(payload, "source_receipt_id")
    if receipt_id is None:
        return None
    record = receipts.get(receipt_id)
    if record is None or record.mission_id != event.mission_id:
        raise MissionHistoryIntegrityError("Referenced execution receipt is missing or belongs to another Mission.")
    sequence = _scalar(payload, "receipt_sequence", int)
    receipt_hash = _text(payload, "receipt_hash")
    if sequence is not None and sequence != record.sequence:
        raise MissionHistoryIntegrityError("Referenced execution receipt sequence does not match.")
    if receipt_hash is not None and receipt_hash != record.receipt_hash:
        raise MissionHistoryIntegrityError("Referenced execution receipt hash does not match.")
    return _receipt_summary(record)


def _resolve_checkpoint(event, payload: Mapping[str, Any], checkpoints: Mapping[str, MissionCheckpointRecord]) -> MissionHistoryCheckpointSummary | None:
    checkpoint_id = _text(payload, "checkpoint_id") or _text(payload, "recovery_checkpoint_id")
    if checkpoint_id is None:
        return None
    record = checkpoints.get(checkpoint_id)
    if record is None or record.mission_id != event.mission_id:
        raise MissionHistoryIntegrityError("Referenced Mission checkpoint is missing or belongs to another Mission.")
    sequence = _scalar(payload, "checkpoint_sequence", int)
    checkpoint_hash = _text(payload, "checkpoint_hash")
    if sequence is not None and sequence != record.sequence:
        raise MissionHistoryIntegrityError("Referenced Mission checkpoint sequence does not match.")
    if checkpoint_hash is not None and checkpoint_hash != record.checkpoint_hash:
        raise MissionHistoryIntegrityError("Referenced Mission checkpoint hash does not match.")
    return _checkpoint_summary(record)


def _failure(payload: Mapping[str, Any]) -> MissionHistoryFailureSummary | None:
    required = ("failure_id", "failure_fingerprint", "phase", "category", "severity", "error_code", "recommended_action")
    values = {key: _text(payload, key) for key in required}
    if any(value is None for value in values.values()):
        raise MissionHistoryIntegrityError("Mission failure event lacks required typed fields.")
    return MissionHistoryFailureSummary(
        **values,
        source_receipt_id=_text(payload, "source_receipt_id"),
        retryable=bool(_boolean(payload, "retryable")),
        recoverable=bool(_boolean(payload, "recoverable")),
        task_attempt=_scalar(payload, "task_attempt", int) or 0,
        mission_recovery_count=_scalar(payload, "mission_recovery_count", int) or 0,
    )


def _recovery(event_type: str, payload: Mapping[str, Any]) -> MissionHistoryRecoverySummary | None:
    status = _RECOVERY_STATUS.get(event_type)
    if status is None:
        return None
    return MissionHistoryRecoverySummary(
        status=status,
        failure_id=_text(payload, "failure_id"),
        category=_text(payload, "category"),
        recovery_attempts_for_failure=_scalar(payload, "recovery_attempts_for_failure", int) or 0,
        recovery_count=_scalar(payload, "recovery_count", int) or 0,
        recovery_checkpoint_id=_text(payload, "recovery_checkpoint_id"),
        control_version=_scalar(payload, "control_version", int),
        scheduled=_boolean(payload, "scheduled"),
    )


def build_mission_history_page(
    *,
    command: SupervisorCommand,
    event_page: MissionEventPage,
    receipts_by_id: Mapping[str, ExecutionReceipt],
    checkpoints_by_id: Mapping[str, MissionCheckpointRecord],
) -> MissionHistoryPage:
    entries: list[MissionHistoryEntry] = []
    for event in event_page.events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        entries.append(MissionHistoryEntry(
            sequence=event.sequence,
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            canonical_kind=event.canonical_kind,
            actor=event.actor,
            task_id=event.task_id,
            approval_id=event.approval_id,
            label=_LABELS.get(event.event_type, event.event_type.replace("_", " ").strip().capitalize())[:160],
            command_status=_text(payload, "command_status", 80),
            task_status=_text(payload, "task_status", 80),
            receipt=_resolve_receipt(event, payload, receipts_by_id),
            checkpoint=_resolve_checkpoint(event, payload, checkpoints_by_id),
            failure=_failure(payload) if event.event_type == "mission_failure_classified" else None,
            recovery=_recovery(event.event_type, payload),
            event_hash=event.event_hash,
        ))
    return MissionHistoryPage(
        mission_id=command.id,
        command_status=command.status,
        terminal=command.status in {"completed", "failed"},
        entries=entries,
        count=len(entries),
        after_sequence=event_page.after_sequence,
        next_after_sequence=event_page.next_after_sequence,
        has_more=event_page.has_more,
        source=event_page.source,
        integrity_verified=event_page.integrity_verified,
        last_sequence=event_page.last_sequence,
        last_event_hash=event_page.last_event_hash,
    )


def compute_mission_summary_fingerprint(summary_payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(summary_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _duration(created_at: str, updated_at: str) -> int | None:
    try:
        created = datetime.fromisoformat(created_at)
        updated = datetime.fromisoformat(updated_at)
    except (TypeError, ValueError):
        return None
    if updated < created:
        return None
    return int((updated - created).total_seconds() * 1000)


def build_mission_post_run_summary(
    *,
    command: SupervisorCommand,
    event_page: MissionEventPage,
    receipts: Sequence[ExecutionReceipt],
    checkpoints: Sequence[MissionCheckpointRecord],
) -> MissionPostRunSummary:
    if command.status not in {"completed", "failed"}:
        raise ValueError("Post-run summary is available only for completed or failed Missions.")
    task_summaries = [MissionTaskPostRunSummary(
        task_id=task.id,
        title=task.title[:500],
        status=task.status,
        attempts=task.attempts,
        verification_failures=task.verification_failures,
        continuation_resumes=task.continuation_resumes,
        recovery_reason=(task.recovery_reason or "")[:300] or None,
        materialized_file_count=len(set(task.materialized_files)),
        approval_count=len({record.approval_id for record in task.approval_history}),
    ) for task in command.tasks]
    completed = sum(task.status == "completed" for task in command.tasks)
    failed = sum(task.status in {"failed", "rework_required"} for task in command.tasks)
    waiting = sum(
        task.status not in {"completed", "failed", "rework_required"}
        and (task.status == "awaiting_approval" or task.approval_state == "pending")
        for task in command.tasks
    )
    other = len(command.tasks) - completed - failed - waiting
    outcomes = {name: sum(receipt.outcome == name for receipt in receipts) for name in ("succeeded", "failed", "cancelled", "timed_out")}
    receipt_refs = {_text(event.payload, key) for event in event_page.events for key in ("receipt_id", "source_receipt_id")}
    checkpoint_refs = {_text(event.payload, key) for event in event_page.events for key in ("checkpoint_id", "recovery_checkpoint_id")}
    receipt_refs.discard(None)
    checkpoint_refs.discard(None)
    unlinked_receipts = sum(receipt.receipt_id not in receipt_refs for receipt in receipts)
    unlinked_checkpoints = sum(checkpoint.checkpoint_id not in checkpoint_refs for checkpoint in checkpoints)
    failure_count = sum(event.event_type == "mission_failure_classified" for event in event_page.events)
    approval_ids = {record.approval_id for task in command.tasks for record in task.approval_history}
    highlights = [
        "Mission completed successfully." if command.status == "completed" else "Mission failed.",
        f"{completed}/{len(command.tasks)} tasks completed.",
        f"{len(receipts)} execution receipts and {len(checkpoints)} checkpoints verified.",
    ]
    if command.recovery_count:
        highlights.append(f"{command.recovery_count} explicit recovery attempts recorded.")
    if failure_count:
        highlights.append(f"{failure_count} classified failure events recorded.")
    warnings: list[str] = []
    if event_page.source == "legacy_command_events":
        warnings.append("Mission history uses legacy command events and is not journal-integrity verified.")
    if unlinked_receipts:
        warnings.append(f"{unlinked_receipts} execution receipts are not linked from Mission events.")
    if unlinked_checkpoints:
        warnings.append(f"{unlinked_checkpoints} Mission checkpoints are not linked from Mission events.")
    if failed:
        warnings.append(f"{failed} tasks ended in failed or rework-required state.")
    if command.latest_failure:
        warnings.append(f"Latest failure category: {command.latest_failure.category}; error code: {command.latest_failure.error_code}.")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "mission_id": command.id,
        "command_status": command.status,
        "outcome": "succeeded" if command.status == "completed" else "failed",
        "terminal": True,
        "goal": command.goal[:2000],
        "created_at": command.created_at,
        "updated_at": command.updated_at,
        "duration_ms": _duration(command.created_at, command.updated_at),
        "task_count": len(command.tasks),
        "completed_task_count": completed,
        "failed_task_count": failed,
        "waiting_task_count": waiting,
        "other_task_count": other,
        "event_count": len(event_page.events),
        "receipt_count": len(receipts),
        "checkpoint_count": len(checkpoints),
        "failure_count": failure_count,
        "recovery_count": command.recovery_count,
        "resume_count": command.resume_count,
        "approval_count": len(approval_ids),
        "execution_succeeded_count": outcomes["succeeded"],
        "execution_failed_count": outcomes["failed"],
        "execution_cancelled_count": outcomes["cancelled"],
        "execution_timed_out_count": outcomes["timed_out"],
        "total_execution_duration_ms": sum(receipt.duration_ms for receipt in receipts),
        "affected_file_count": len({name for receipt in receipts for name in receipt.affected_files}),
        "artifact_count": len({name for receipt in receipts for name in receipt.artifact_ids}),
        "unlinked_receipt_count": unlinked_receipts,
        "unlinked_checkpoint_count": unlinked_checkpoints,
        "latest_failure": command.latest_failure,
        "tasks": task_summaries,
        "highlights": highlights[:12],
        "warnings": warnings[:12],
        "history_source": event_page.source,
        "integrity_verified": event_page.integrity_verified,
        "last_event_sequence": event_page.last_sequence,
        "last_event_hash": event_page.last_event_hash,
        "last_receipt_sequence": receipts[-1].sequence if receipts else 0,
        "last_receipt_hash": receipts[-1].receipt_hash if receipts else None,
        "last_checkpoint_sequence": checkpoints[-1].sequence if checkpoints else 0,
        "last_checkpoint_hash": checkpoints[-1].checkpoint_hash if checkpoints else None,
    }
    json_payload = MissionPostRunSummary(**payload, summary_fingerprint="sha256:" + "0" * 64).model_dump(mode="json", exclude={"summary_fingerprint"})
    return MissionPostRunSummary(**payload, summary_fingerprint=compute_mission_summary_fingerprint(json_payload))
