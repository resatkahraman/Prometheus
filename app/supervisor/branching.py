from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.supervisor.models import (
    MissionBranchSummary,
    MissionLineageResponse,
    MissionCheckpointRecord,
    SupervisorCommand,
)


class MissionBranchError(RuntimeError):
    pass


class MissionBranchConflictError(MissionBranchError):
    pass


class MissionBranchIntegrityError(MissionBranchError):
    pass


class MissionBranchUnsupportedSnapshotError(MissionBranchError):
    pass


BRANCH_SNAPSHOT_SCHEMA_VERSION = 2
MAX_MISSION_BRANCH_DEPTH = 64

_SECRET_KEY_COMPONENTS = {
    "password",
    "authorization",
    "cookie",
    "credential",
    "credentials",
}
_SECRET_COMPOSITE_KEYS = {
    "api_key",
    "private_key",
    "session_token",
    "pandora_token",
}
_BENIGN_OPERATIONAL_TOKEN_KEYS = frozenset(
    {
        "blocked_state_token",
        "failure_state_tokens",
    }
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![a-z0-9_])(?:token|access_token|http_auth_token|refresh_token|"
    r"session_token|pandora_token|password|api_key|authorization|cookie|"
    r"credential|credentials|private_key)(?![a-z0-9_])\s*[=:]\s*\S+"
)


def _normalized_snapshot_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold())
    return re.sub(r"_+", "_", normalized).strip("_")


def _is_benign_token_metric_key(normalized_key: str) -> bool:
    if normalized_key == "tokens" or normalized_key.endswith("_tokens"):
        return True
    exact = {"token_count", "token_budget", "token_limit", "token_usage"}
    if normalized_key in exact:
        return True
    return normalized_key.endswith((
        "_token_count",
        "_token_budget",
        "_token_limit",
        "_token_usage",
        "_tokens_used",
        "_tokens_remaining",
    ))


def _is_benign_operational_token_key(normalized_key: str) -> bool:
    return normalized_key in _BENIGN_OPERATIONAL_TOKEN_KEYS


def _is_secret_snapshot_key(key: object) -> bool:
    normalized = _normalized_snapshot_key(key)
    if not normalized:
        return True
    if _is_benign_token_metric_key(normalized):
        return False
    if _is_benign_operational_token_key(normalized):
        return False
    components = set(normalized.split("_"))
    if normalized == "token" or "token" in components:
        return True
    if any(
        normalized == component or normalized.endswith("_" + component)
        for component in _SECRET_KEY_COMPONENTS
    ):
        return True
    return any(
        normalized == composite or normalized.endswith("_" + composite)
        for composite in _SECRET_COMPOSITE_KEYS
    )


def compute_branch_idempotency_key_hash(idempotency_key: str) -> str:
    return "sha256:" + hashlib.sha256(idempotency_key.strip().encode("utf-8")).hexdigest()


def compute_branch_request_fingerprint(*, parent_mission_id: str, checkpoint_id: str, checkpoint_hash: str, idempotency_key_hash: str, label: str | None) -> str:
    payload = {
        "parent_mission_id": parent_mission_id,
        "checkpoint_id": checkpoint_id,
        "checkpoint_hash": checkpoint_hash,
        "idempotency_key_hash": idempotency_key_hash,
        "label": label,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_legacy_checkpoint_snapshot(command: SupervisorCommand) -> dict[str, Any]:
    active_task = next((task for task in command.tasks if task.status == "running"), None)
    return {
        "id": command.id,
        "goal": command.goal,
        "status": command.status,
        "autonomy_mode": command.autonomy_mode,
        "auto_run": command.auto_run,
        "plan_text": command.plan_text,
        "tasks": [{
            "id": task.id, "title": task.title, "status": task.status,
            "attempts": task.attempts, "assigned_agent": task.assigned_agent,
            "verification": task.verification, "exact_files": list(task.exact_files or []),
            "continuation_resumes": task.continuation_resumes,
            "recovery_reason": task.recovery_reason,
        } for task in command.tasks],
        "decisions": [{"id": decision.id, "question": decision.question, "status": decision.status, "answer": decision.answer} for decision in command.decisions],
        "execution_layers": command.execution_layers,
        "current_task_id": active_task.id if active_task else None,
        "control_version": command.control_version,
        "resume_count": command.resume_count,
    }


def _contains_unsafe(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _is_secret_snapshot_key(key):
                return True
            if _contains_unsafe(child):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_unsafe(child) for child in value)
    if isinstance(value, str):
        lowered = value.casefold()
        if "traceback (most recent call last)" in lowered:
            return True
        if _SECRET_ASSIGNMENT_RE.search(value):
            return True
        if any(marker in lowered for marker in ("c:\\users\\", "/home/", "/users/", "/root/", "/tmp/")):
            return True
    if isinstance(value, float) and not math.isfinite(value):
        return True
    if value is None or isinstance(value, (bool, int, str)):
        return False
    return True


def build_branch_checkpoint_snapshot(command: SupervisorCommand) -> dict[str, Any]:
    excluded = {"events", "planning_agent_response", "updated_at", "active_checkpoint_id", "active_operation", "operation_phase", "operation_message", "operation_attempt", "operation_max_attempts", "operation_route", "operation_started_at", "last_heartbeat_at"}
    task_excluded = {"agent_session_id", "last_agent_response", "processing_approval_id"}
    raw = command.model_dump(mode="json")
    state = {key: value for key, value in raw.items() if key not in excluded}
    state["tasks"] = [{key: value for key, value in task.items() if key not in task_excluded} for task in state.get("tasks", [])]
    snapshot = {"snapshot_schema_version": BRANCH_SNAPSHOT_SCHEMA_VERSION, "command_state": state}
    if not isinstance(snapshot, dict) or _contains_unsafe(snapshot):
        raise MissionBranchIntegrityError("Checkpoint snapshot contains unsafe state.")
    try:
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MissionBranchIntegrityError(
            "Checkpoint snapshot is not canonical JSON-safe."
        ) from exc
    if snapshot.get("command_state", {}).get("id") != command.id:
        raise MissionBranchIntegrityError("Checkpoint snapshot Mission ID mismatch.")
    return snapshot


def checkpoint_snapshot_version(snapshot: Mapping[str, Any]) -> int:
    if snapshot.get("snapshot_schema_version") == 2 and isinstance(snapshot.get("command_state"), dict):
        return 2
    if isinstance(snapshot, Mapping) and "id" in snapshot and "tasks" in snapshot and "control_version" in snapshot:
        return 1
    return 0


def validate_branch_source(*, parent: SupervisorCommand, checkpoint: MissionCheckpointRecord, snapshot: Mapping[str, Any]) -> SupervisorCommand:
    version = checkpoint_snapshot_version(snapshot)
    if version == 1:
        raise MissionBranchUnsupportedSnapshotError("Checkpoint snapshot is not branch-capable.")
    if version != 2:
        raise MissionBranchIntegrityError("Checkpoint snapshot version is invalid.")
    state = snapshot["command_state"]
    if checkpoint.mission_id != parent.id or state.get("id") != parent.id:
        raise MissionBranchIntegrityError("Checkpoint source Mission mismatch.")
    try:
        source = SupervisorCommand.model_validate(state)
    except Exception as exc:
        raise MissionBranchIntegrityError("Checkpoint command state is invalid.") from exc
    if source.status != checkpoint.status_at_checkpoint or source.control_version != checkpoint.state_version:
        raise MissionBranchIntegrityError("Checkpoint state does not match its command.")
    if any(task.status == "running" for task in source.tasks):
        raise MissionBranchIntegrityError("Checkpoint contains a running task.")
    if source.status in {"planning", "completed", "failed"}:
        raise MissionBranchIntegrityError("Mission state cannot be branched.")
    if source.status == "paused" and not (source.resume_target_status or checkpoint.resume_target_status):
        raise MissionBranchIntegrityError("Paused checkpoint has no resume target.")
    return source


def build_child_branch_command(*, source_command: SupervisorCommand, parent: SupervisorCommand, checkpoint: MissionCheckpointRecord, child_mission_id: str, request_fingerprint: str, idempotency_key_hash: str, label: str | None, now: datetime) -> tuple[SupervisorCommand, str]:
    target = source_command.resume_target_status if source_command.status == "paused" else checkpoint.resume_target_status if source_command.status == "paused" else source_command.status
    if source_command.status == "running":
        target = "ready"
    if target not in {"ready", "awaiting_approval", "waiting_decision", "reviewing", "rework_required"}:
        raise MissionBranchIntegrityError("Branch resume target is invalid.")
    child = deepcopy(source_command)
    child.id = child_mission_id
    child.root_mission_id = parent.root_mission_id or parent.id
    child.parent_mission_id = parent.id
    child.source_checkpoint_id = checkpoint.checkpoint_id
    child.source_checkpoint_sequence = checkpoint.sequence
    child.source_checkpoint_hash = checkpoint.checkpoint_hash
    child.source_checkpoint_state_hash = checkpoint.state_hash
    child.branch_depth = parent.branch_depth + 1
    if child.branch_depth > MAX_MISSION_BRANCH_DEPTH:
        raise MissionBranchConflictError("Maximum branch depth exceeded.")
    child.branch_label = label
    child.branch_idempotency_key_hash = idempotency_key_hash
    child.branch_request_fingerprint = request_fingerprint
    child.branched_at = now
    child.branch_activation_required = True
    child.branch_activated_at = None
    child.branch_workspace_mode = "shared_current_workspace"
    child.status = "paused"
    child.auto_run = False
    child.archived = False
    child.archived_at = None
    child.pause_requested = False
    child.pause_requested_at = None
    child.pause_reason = None
    child.paused_at = now
    child.active_checkpoint_id = None
    child.resume_target_status = target
    child.control_version = 0
    child.resume_count = 0
    child.active_operation = child.operation_phase = child.operation_message = child.operation_route = child.operation_started_at = child.last_heartbeat_at = None
    child.operation_attempt = child.operation_max_attempts = 0
    child.events = []
    child.planning_agent_response = None
    stamp = now.isoformat()
    child.created_at = stamp
    child.updated_at = stamp
    for task in child.tasks:
        task.agent_session_id = None
        task.last_agent_response = None
        task.processing_approval_id = None
    return child, target


def build_mission_lineage(*, command: SupervisorCommand, commands: Sequence[SupervisorCommand]) -> MissionLineageResponse:
    index = {item.id: item for item in commands}
    ancestors: list[str] = []
    current = command
    complete = True
    seen: set[str] = set()
    while current.parent_mission_id:
        if current.id in seen or len(ancestors) >= MAX_MISSION_BRANCH_DEPTH:
            raise MissionBranchIntegrityError("Mission lineage cycle or depth violation.")
        seen.add(current.id)
        ancestors.append(current.parent_mission_id)
        current = index.get(current.parent_mission_id)
        if current is None:
            complete = False
            break
    root = command.root_mission_id or (current.id if current else command.id)
    children = sorted((item for item in commands if item.parent_mission_id == command.id), key=lambda item: (item.created_at, item.id))
    summaries = [MissionBranchSummary(mission_id=item.id, status=item.status, branch_depth=item.branch_depth, source_checkpoint_id=item.source_checkpoint_id or "unknown", source_checkpoint_sequence=item.source_checkpoint_sequence or 1, source_checkpoint_hash=item.source_checkpoint_hash or "sha256:" + "0" * 64, branch_label=item.branch_label, created_at=item.created_at, activation_required=item.branch_activation_required, activated_at=item.branch_activated_at) for item in children]
    return MissionLineageResponse(mission_id=command.id, root_mission_id=root, parent_mission_id=command.parent_mission_id, branch_depth=command.branch_depth, source_checkpoint_id=command.source_checkpoint_id, source_checkpoint_sequence=command.source_checkpoint_sequence, source_checkpoint_hash=command.source_checkpoint_hash, source_checkpoint_state_hash=command.source_checkpoint_state_hash, ancestor_mission_ids=ancestors, direct_children=summaries, direct_child_count=len(summaries), lineage_complete=complete)
