from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
from typing import Any, Mapping
import uuid

from app.supervisor.models import (
    MissionEventIntegrity,
    MissionEventPage,
    MissionEventRecord,
    MissionStateProjection,
)


class MissionEventJournalError(RuntimeError):
    pass


class MissionEventIntegrityError(MissionEventJournalError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        error_sequence: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_sequence = error_sequence


SECRET_DENYLIST = {
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "credential",
    "private_key",
    "session_token",
    "pandora_token",
}


def canonical_event_kind(event_type: str) -> str:
    et = (event_type or "").strip().lower()

    # 1. approval
    if (
        et.startswith("approval_")
        or et.startswith("decision_")
        or "_approval_" in et
        or et.endswith("_approval")
    ):
        return "approval"

    # 2. checkpoint
    if et.startswith("checkpoint_") or et in ("mission_paused", "mission_resumed"):
        return "checkpoint"

    # 3. recovery
    if et.startswith("recovery_") or et.startswith("retry_"):
        return "recovery"

    # 4. tool
    if (
        et.startswith("tool_")
        or et.startswith("workspace_")
        or et.startswith("run_snapshot_")
        or et.startswith("run_changes_")
        or et.startswith("git_run_")
    ):
        return "tool"

    # 5. step
    if (
        et.startswith("task_")
        or et.startswith("step_")
        or et.startswith("verification_")
        or et.startswith("deterministic_contract_repair_")
    ):
        return "step"

    # 6. plan
    if et.startswith("plan_") or et.startswith("planning_") or et.startswith("retry_planning_"):
        return "plan"

    # 7. mission
    if et in (
        "command_created",
        "mission_created",
        "command_started",
        "mission_started",
        "command_completed",
        "mission_completed",
        "command_failed",
        "mission_failed",
        "command_cancelled",
        "mission_cancelled",
    ):
        return "mission"

    # 8. system
    return "system"


def sanitize_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return _sanitize_dict(dict(payload), depth=0)


def _sanitize_value(val: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[NESTING_LIMIT_EXCEEDED]"
    if val is None or isinstance(val, (bool, int)):
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    if isinstance(val, str):
        if len(val) > 20000:
            return val[:20000] + "...[TRUNCATED]"
        return val
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        else:
            val = val.astimezone(timezone.utc)
        return val.isoformat()
    if isinstance(val, Path):
        s = str(val)
        if len(s) > 20000:
            s = s[:20000] + "...[TRUNCATED]"
        return s
    if isinstance(val, bytes):
        return f"[BYTES:{len(val)}]"
    if isinstance(val, Exception):
        return f"[{type(val).__name__}]"
    if isinstance(val, Mapping):
        return _sanitize_dict(dict(val), depth=depth + 1)
    if isinstance(val, (list, tuple, set)):
        items = list(val)[:200]
        return [_sanitize_value(item, depth=depth + 1) for item in items]
    s = str(val)
    if len(s) > 20000:
        s = s[:20000] + "...[TRUNCATED]"
    return s


def _sanitize_dict(d: dict[Any, Any], depth: int = 0) -> dict[str, Any]:
    if depth > 8:
        return {"[LIMIT]": "[NESTING_LIMIT_EXCEEDED]"}
    result: dict[str, Any] = {}
    keys = list(d.keys())[:200]
    for k in keys:
        key_str = str(k)
        if len(key_str) > 200:
            key_str = key_str[:200]
        if key_str.lower() in SECRET_DENYLIST:
            result[key_str] = "[REDACTED]"
        else:
            result[key_str] = _sanitize_value(d[k], depth=depth + 1)
    return result


def compute_canonical_event_hash(
    *,
    schema_version: int,
    event_id: str,
    mission_id: str,
    sequence: int,
    event_type: str,
    canonical_kind: str,
    occurred_at_iso: str,
    task_id: str | None,
    approval_id: str | None,
    actor: str,
    payload: dict[str, Any],
    previous_hash: str | None,
) -> str:
    canonical_dict = {
        "schema_version": schema_version,
        "event_id": event_id,
        "mission_id": mission_id,
        "sequence": sequence,
        "event_type": event_type,
        "canonical_kind": canonical_kind,
        "occurred_at": occurred_at_iso,
        "task_id": task_id,
        "approval_id": approval_id,
        "actor": actor,
        "payload": payload,
        "previous_hash": previous_hash,
    }
    canonical_bytes = json.dumps(
        canonical_dict,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


class MissionEventJournal:
    def __init__(
        self,
        *,
        root: Path | None,
        persistence_enabled: bool,
    ) -> None:
        self.persistence_enabled = persistence_enabled and (root is not None)
        if self.persistence_enabled and root is not None:
            self._journal_dir: Path | None = root / "mission_events"
            self._journal_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._journal_dir = None

        self._memory_cache: dict[str, list[MissionEventRecord]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_mission_lock(self, mission_id: str) -> threading.Lock:
        with self._global_lock:
            lock = self._locks.get(mission_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[mission_id] = lock
            return lock

    def _get_journal_file_path(self, mission_id: str) -> Path | None:
        if not self.persistence_enabled or self._journal_dir is None:
            return None
        safe_key = hashlib.sha256(mission_id.encode("utf-8")).hexdigest()
        return self._journal_dir / f"{safe_key}.jsonl"

    def has_journal(self, *, mission_id: str) -> bool:
        path = self._get_journal_file_path(mission_id)
        if path is not None and path.is_file() and path.stat().st_size > 0:
            return True
        mem = self._memory_cache.get(mission_id)
        return bool(mem)

    def _read_and_verify_disk_events(self, mission_id: str) -> list[MissionEventRecord]:
        path = self._get_journal_file_path(mission_id)
        if path is None or not path.is_file():
            return []

        try:
            raw_bytes = path.read_bytes()
        except Exception as exc:
            raise MissionEventIntegrityError(
                f"Journal file unreadable: {exc}",
                error_code="journal_invalid_utf8",
                error_sequence=1,
            ) from exc

        if not raw_bytes:
            return []

        lines = raw_bytes.split(b"\n")
        # Trailing empty line after final \n is expected
        if lines and lines[-1] == b"":
            lines.pop()
        else:
            # Trailing byte line without \n is partial line corruption
            raise MissionEventIntegrityError(
                "Journal file has trailing partial line without newline.",
                error_code="journal_invalid_json",
                error_sequence=len(lines),
            )

        events: list[MissionEventRecord] = []

        for idx, line in enumerate(lines, start=1):
            try:
                line_str = line.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MissionEventIntegrityError(
                    f"Invalid UTF-8 at sequence {idx}: {exc}",
                    error_code="journal_invalid_utf8",
                    error_sequence=idx,
                ) from exc

            try:
                data = json.loads(line_str)
            except json.JSONDecodeError as exc:
                raise MissionEventIntegrityError(
                    f"Invalid JSON at sequence {idx}: {exc}",
                    error_code="journal_invalid_json",
                    error_sequence=idx,
                ) from exc

            if not isinstance(data, dict):
                raise MissionEventIntegrityError(
                    f"Record at sequence {idx} is not a JSON object.",
                    error_code="journal_invalid_record",
                    error_sequence=idx,
                )

            if data.get("mission_id") != mission_id:
                raise MissionEventIntegrityError(
                    f"Mission ID mismatch at sequence {idx}: expected '{mission_id}', got '{data.get('mission_id')}'",
                    error_code="journal_mission_mismatch",
                    error_sequence=idx,
                )

            if data.get("sequence") != idx:
                raise MissionEventIntegrityError(
                    f"Sequence gap at record {idx}: expected {idx}, got {data.get('sequence')}",
                    error_code="journal_sequence_gap",
                    error_sequence=idx,
                )

            try:
                rec = MissionEventRecord.model_validate(data)
            except Exception as exc:
                raise MissionEventIntegrityError(
                    f"Invalid record at sequence {idx}: {exc}",
                    error_code="journal_invalid_record",
                    error_sequence=idx,
                ) from exc

            expected_prev_hash = events[-1].event_hash if events else None
            if rec.previous_hash != expected_prev_hash:
                raise MissionEventIntegrityError(
                    f"Previous hash mismatch at sequence {idx}: expected {expected_prev_hash}, got {rec.previous_hash}",
                    error_code="journal_previous_hash_mismatch",
                    error_sequence=idx,
                )

            recomputed_hash = compute_canonical_event_hash(
                schema_version=rec.schema_version,
                event_id=rec.event_id,
                mission_id=rec.mission_id,
                sequence=rec.sequence,
                event_type=rec.event_type,
                canonical_kind=rec.canonical_kind,
                occurred_at_iso=rec.occurred_at.astimezone(timezone.utc).isoformat(),
                task_id=rec.task_id,
                approval_id=rec.approval_id,
                actor=rec.actor,
                payload=rec.payload,
                previous_hash=rec.previous_hash,
            )

            if recomputed_hash != rec.event_hash:
                raise MissionEventIntegrityError(
                    f"Event hash mismatch at sequence {idx}: computed '{recomputed_hash}', record has '{rec.event_hash}'",
                    error_code="journal_event_hash_mismatch",
                    error_sequence=idx,
                )

            events.append(rec)

        return events

    def append(
        self,
        *,
        mission_id: str,
        event_type: str,
        canonical_kind: str | None = None,
        occurred_at: datetime | None = None,
        task_id: str | None = None,
        approval_id: str | None = None,
        actor: str = "supervisor",
        payload: Mapping[str, Any] | None = None,
    ) -> MissionEventRecord:
        lock = self._get_mission_lock(mission_id)
        with lock:
            if self.persistence_enabled:
                existing_events = self._read_and_verify_disk_events(mission_id)
            else:
                existing_events = self._memory_cache.get(mission_id, [])

            seq = len(existing_events) + 1
            prev_hash = existing_events[-1].event_hash if existing_events else None

            kind = canonical_kind or canonical_event_kind(event_type)

            dt = occurred_at or datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            dt_iso = dt.isoformat()

            t_id = task_id.strip() if task_id and task_id.strip() else None
            a_id = approval_id.strip() if approval_id and approval_id.strip() else None
            act = (actor or "supervisor").strip() or "supervisor"

            clean_payload = sanitize_payload(payload)

            ev_id = uuid.uuid4().hex

            ev_hash = compute_canonical_event_hash(
                schema_version=1,
                event_id=ev_id,
                mission_id=mission_id,
                sequence=seq,
                event_type=event_type.strip(),
                canonical_kind=kind,
                occurred_at_iso=dt_iso,
                task_id=t_id,
                approval_id=a_id,
                actor=act,
                payload=clean_payload,
                previous_hash=prev_hash,
            )

            record = MissionEventRecord(
                schema_version=1,
                event_id=ev_id,
                mission_id=mission_id,
                sequence=seq,
                event_type=event_type.strip(),
                canonical_kind=kind,
                occurred_at=dt,
                task_id=t_id,
                approval_id=a_id,
                actor=act,
                payload=clean_payload,
                previous_hash=prev_hash,
                event_hash=ev_hash,
            )

            if self.persistence_enabled:
                path = self._get_journal_file_path(mission_id)
                assert path is not None
                line_bytes = record.model_dump_json(exclude_none=False).encode("utf-8") + b"\n"
                try:
                    with open(path, "ab") as f:
                        f.write(line_bytes)
                        f.flush()
                        os.fsync(f.fileno())
                except Exception as exc:
                    raise MissionEventJournalError(f"Failed to append event to disk: {exc}") from exc

            # Update memory cache
            cache_list = self._memory_cache.setdefault(mission_id, [])
            cache_list.append(record)

            return record

    def list_events(
        self,
        *,
        mission_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[MissionEventRecord]:
        lock = self._get_mission_lock(mission_id)
        with lock:
            if self.persistence_enabled and self.has_journal(mission_id=mission_id):
                events = self._read_and_verify_disk_events(mission_id)
            else:
                events = self._memory_cache.get(mission_id, [])

            filtered = [ev for ev in events if ev.sequence > after_sequence]
            return filtered[:limit]

    def verify(
        self,
        *,
        mission_id: str,
    ) -> MissionEventIntegrity:
        lock = self._get_mission_lock(mission_id)
        with lock:
            try:
                if self.persistence_enabled and self.has_journal(mission_id=mission_id):
                    events = self._read_and_verify_disk_events(mission_id)
                else:
                    events = self._memory_cache.get(mission_id, [])
                last_seq = events[-1].sequence if events else 0
                last_hash = events[-1].event_hash if events else None
                return MissionEventIntegrity(
                    mission_id=mission_id,
                    valid=True,
                    event_count=len(events),
                    last_sequence=last_seq,
                    last_event_hash=last_hash,
                    error_code=None,
                    error_sequence=None,
                )
            except MissionEventIntegrityError as exc:
                return MissionEventIntegrity(
                    mission_id=mission_id,
                    valid=False,
                    event_count=0,
                    last_sequence=0,
                    last_event_hash=None,
                    error_code=exc.error_code,
                    error_sequence=exc.error_sequence,
                )

    def project_state(
        self,
        *,
        mission_id: str,
    ) -> MissionStateProjection:
        events = self.list_events(mission_id=mission_id, limit=100000)

        if not events:
            return MissionStateProjection(
                mission_id=mission_id,
                event_count=0,
                last_sequence=0,
                last_event_type=None,
                command_status=None,
                task_statuses={},
                pending_approval_ids=[],
                terminal=False,
            )

        cmd_status: str | None = None
        task_stats: dict[str, str] = {}
        pending_apps: list[str] = []

        for ev in events:
            p = ev.payload or {}
            c_stat = p.get("command_status")
            if isinstance(c_stat, str) and c_stat:
                cmd_status = c_stat

            t_id = ev.task_id
            t_stat = p.get("task_status")
            if t_id and isinstance(t_stat, str) and t_stat:
                task_stats[t_id] = t_stat

            p_apps = p.get("pending_approval_ids")
            if isinstance(p_apps, list):
                clean_p_apps = [str(x) for x in p_apps if isinstance(x, str) and x]
                # Maintain stable unique order
                seen = set()
                uniq_p_apps = []
                for item in clean_p_apps:
                    if item not in seen:
                        seen.add(item)
                        uniq_p_apps.append(item)
                pending_apps = uniq_p_apps

        terminal = cmd_status in {"completed", "failed", "cancelled", "reverted"}

        return MissionStateProjection(
            mission_id=mission_id,
            event_count=len(events),
            last_sequence=events[-1].sequence,
            last_event_type=events[-1].event_type,
            command_status=cmd_status,
            task_statuses=task_stats,
            pending_approval_ids=pending_apps,
            terminal=terminal,
        )
