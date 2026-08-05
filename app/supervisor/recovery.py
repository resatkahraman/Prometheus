from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid

from app.supervisor.checkpoints import MissionCheckpointIntegrityError
from app.supervisor.event_journal import MissionEventIntegrityError
from app.supervisor.execution_receipts import ExecutionReceiptIntegrityError
from app.supervisor.models import MissionFailureClassification


MAX_RECOVERY_ATTEMPTS_PER_FAILURE = 1
MAX_MISSION_RECOVERIES = 3


@dataclass(frozen=True)
class FailureSignal:
    mission_id: str
    phase: str
    error_code: str
    safe_message: str
    task_id: str | None = None
    source_receipt_id: str | None = None
    task_attempt: int = 0
    exception: BaseException | None = None
    receipt_outcome: str | None = None
    verification_failed: bool = False


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(token|password|api[_-]?key|authorization|cookie|credential|"
    r"private[_-]?key|session[_-]?token)\b\s*[:=]\s*([^\s,;]+)"
)
_WINDOWS_PATH = re.compile(r"(?i)(?<![\w])(?:[a-z]:\\|\\\\)[^\s\"'<>]+")
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:home|users|root|var|tmp|etc)/[^\s\"'<>]+", re.I)
_TRACEBACK = re.compile(r"(?is)traceback\s*\(most recent call last\).*?(?:\n\s*\n|$)")


def _code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return normalized.strip("_")[:160] or "unknown"


def sanitize_failure_message(value: str, *, fallback: str) -> str:
    text = _TRACEBACK.sub("[REDACTED]", value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SECRET_ASSIGNMENT.sub("[REDACTED]", text)
    text = _WINDOWS_PATH.sub("[REDACTED_PATH]", text)
    text = _POSIX_PATH.sub("[REDACTED_PATH]", text)
    text = "\n".join(part.strip() for part in text.split("\n") if part.strip())
    return (text or fallback)[:2000]


def _classification(
    code: str,
    signal: FailureSignal,
) -> tuple[str, str, bool, bool, str]:
    exc = signal.exception
    if code in {"timeout", "operation_timeout", "provider_timeout", "focused_provider_timeout", "verification_timeout"} or isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "timeout", "error", True, True, "retry_task"
    if code in {"rate_limited", "provider_rate_limited", "http_429", "quota_temporarily_unavailable"}:
        return "rate_limited", "warning", True, True, "retry_task"
    if code in {"transient_provider", "provider_transient_error", "provider_connection_reset", "provider_temporary_failure"}:
        return "transient_provider", "warning", True, True, "retry_task"
    if code in {"dependency_unavailable", "provider_unavailable", "route_unavailable", "connection_error", "network_unavailable"} or isinstance(exc, ConnectionError):
        return "dependency_unavailable", "error", True, True, "retry_task"
    if signal.verification_failed or code in {"verification_failed", "verification_nonzero_exit", "assertion_failure", "contract_verification_failed"}:
        return "verification_failed", "error", True, True, "retry_task"
    if code in {"approval_rejected", "user_rejected", "approval_denied"}:
        return "approval_rejected", "warning", False, False, "request_approval"
    if code in {"policy_blocked", "budget_exhausted", "scope_violation", "approval_required", "unsafe_operation", "attempt_limit_exhausted"}:
        return "policy_blocked", "error", False, False, "manual_intervention"
    if code in {"state_conflict", "checkpoint_state_conflict", "control_version_conflict", "active_checkpoint_mismatch"}:
        return "state_conflict", "critical", False, False, "manual_intervention"
    if code in {"integrity_failure", "checkpoint_integrity_error", "event_integrity_error", "receipt_integrity_error", "hash_mismatch", "sequence_gap"} or isinstance(exc, (MissionCheckpointIntegrityError, MissionEventIntegrityError, ExecutionReceiptIntegrityError)):
        return "integrity_failure", "critical", False, False, "none"
    if code in {"cancelled", "user_cancelled", "operation_cancelled"} or isinstance(exc, asyncio.CancelledError):
        return "cancelled", "warning", False, False, "none"
    if code in {"invalid_request", "validation_error", "invalid_task_state", "not_found"}:
        return "invalid_request", "error", False, False, "manual_intervention"
    if exc is not None or code in {"internal_error", "runtime_error", "programming_error"}:
        return "internal_error", "critical", False, False, "manual_intervention"
    return "unknown", "error", False, False, "manual_intervention"


def classify_mission_failure(
    signal: FailureSignal,
    *,
    mission_recovery_count: int,
) -> MissionFailureClassification:
    code = _code(signal.error_code)
    category, severity, retryable, recoverable, action = _classification(code, signal)
    fingerprint_source = {
        "mission_id": signal.mission_id.strip(),
        "task_id": (signal.task_id or "").strip() or None,
        "phase": _code(signal.phase),
        "error_code": code,
        "category": category,
        "task_attempt": max(0, signal.task_attempt),
        "source_receipt_id": (signal.source_receipt_id or "").strip() or None,
        "receipt_outcome": _code(signal.receipt_outcome or "unknown"),
        "verification_failed": bool(signal.verification_failed),
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    fallback = {
        "timeout": "İşlem zaman aşımına uğradı.",
        "rate_limited": "Geçici hız sınırına ulaşıldı.",
        "transient_provider": "Sağlayıcı geçici olarak yanıt veremedi.",
        "dependency_unavailable": "Gerekli bağımlılık geçici olarak kullanılamıyor.",
        "verification_failed": "Doğrulama başarısız oldu.",
    }.get(category, "Mission güvenli biçimde durduruldu.")
    return MissionFailureClassification(
        failure_id=uuid.uuid4().hex,
        failure_fingerprint=f"sha256:{digest}",
        mission_id=signal.mission_id,
        task_id=signal.task_id,
        source_receipt_id=signal.source_receipt_id,
        occurred_at=datetime.now(timezone.utc),
        phase=_code(signal.phase) if _code(signal.phase) in {
            "planning", "task_execution", "verification", "review", "approval",
            "checkpoint", "resume", "background", "unknown",
        } else "unknown",
        category=category,
        severity=severity,
        error_code=code,
        safe_message=sanitize_failure_message(signal.safe_message, fallback=fallback),
        retryable=retryable,
        recoverable=recoverable,
        recommended_action=action,
        task_attempt=max(0, signal.task_attempt),
        mission_recovery_count=max(0, mission_recovery_count),
    )
