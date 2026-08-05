import os
import json
import hashlib
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.supervisor.models import (
    MissionCheckpointRecord,
    MissionCheckpointIntegrity,
)


class MissionCheckpointError(RuntimeError):
    pass


class MissionCheckpointIntegrityError(MissionCheckpointError):
    pass


class DuplicateMissionCheckpointError(MissionCheckpointError):
    pass


def compute_state_hash(snapshot: Mapping[str, Any]) -> tuple[str, int]:
    json_bytes = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(json_bytes).hexdigest()
    return f"sha256:{digest}", len(json_bytes)


def compute_canonical_checkpoint_hash(
    *,
    schema_version: int,
    checkpoint_id: str,
    mission_id: str,
    sequence: int,
    created_at_iso: str,
    reason: str,
    status_at_checkpoint: str,
    resume_target_status: str | None,
    current_task_id: str | None,
    pending_approval_ids: Sequence[str],
    state_version: int,
    state_hash: str,
    snapshot_size_bytes: int,
    resumable: bool,
    previous_checkpoint_hash: str | None,
) -> str:
    payload = {
        "schema_version": schema_version,
        "checkpoint_id": checkpoint_id.strip(),
        "mission_id": mission_id.strip(),
        "sequence": sequence,
        "created_at": created_at_iso,
        "reason": reason,
        "status_at_checkpoint": status_at_checkpoint,
        "resume_target_status": resume_target_status,
        "current_task_id": current_task_id,
        "pending_approval_ids": list(pending_approval_ids),
        "state_version": state_version,
        "state_hash": state_hash,
        "snapshot_size_bytes": snapshot_size_bytes,
        "resumable": resumable,
        "previous_checkpoint_hash": previous_checkpoint_hash,
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class MissionCheckpointStore:
    def __init__(
        self,
        *,
        root: Path | None,
        persistence_enabled: bool,
    ) -> None:
        self.root = root
        self.persistence_enabled = bool(persistence_enabled and root is not None)
        self._memory_store: dict[str, list[dict[str, Any]]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

        if self.persistence_enabled and self.root is not None:
            self.checkpoints_dir = self.root / "mission_checkpoints"
            self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock(self, mission_id: str) -> threading.Lock:
        with self._global_lock:
            if mission_id not in self._locks:
                self._locks[mission_id] = threading.Lock()
            return self._locks[mission_id]

    def _checkpoint_file_path(self, mission_id: str) -> Path | None:
        if not self.persistence_enabled or self.root is None:
            return None
        hashed_name = hashlib.sha256(mission_id.encode("utf-8")).hexdigest()
        return self.root / "mission_checkpoints" / f"{hashed_name}.jsonl"

    def has_checkpoints(self, *, mission_id: str) -> bool:
        if not mission_id or not mission_id.strip():
            return False
        path = self._checkpoint_file_path(mission_id)
        if path is not None:
            return path.exists() and path.stat().st_size > 0
        return mission_id in self._memory_store and len(self._memory_store[mission_id]) > 0

    def _read_and_verify_disk_records(
        self,
        mission_id: str,
    ) -> list[tuple[MissionCheckpointRecord, dict[str, Any]]]:
        path = self._checkpoint_file_path(mission_id)
        if path is None or not path.exists():
            return []

        results: list[tuple[MissionCheckpointRecord, dict[str, Any]]] = []
        previous_hash: str | None = None
        seen_ids: set[str] = set()

        try:
            with open(path, "rb") as f:
                content = f.read()
        except Exception as exc:
            raise MissionCheckpointIntegrityError(
                f"Failed to read checkpoint file for mission '{mission_id}': {exc}"
            ) from exc

        if not content:
            return []

        if not content.endswith(b"\n"):
            raise MissionCheckpointIntegrityError(
                f"Trailing partial JSON line detected in checkpoint file for mission '{mission_id}'."
            )

        lines = content.decode("utf-8").splitlines()
        for idx, line in enumerate(lines, start=1):
            if not line.strip():
                raise MissionCheckpointIntegrityError(
                    f"Empty or whitespace line in checkpoint file for mission '{mission_id}' at sequence {idx}."
                )
            try:
                raw_data = json.loads(line)
            except Exception as exc:
                raise MissionCheckpointIntegrityError(
                    f"Invalid JSON at sequence {idx} for mission '{mission_id}': {exc}"
                ) from exc

            if not isinstance(raw_data, dict):
                raise MissionCheckpointIntegrityError(
                    f"Record at sequence {idx} is not a JSON object for mission '{mission_id}'."
                )

            file_m_id = raw_data.get("mission_id")
            if file_m_id != mission_id:
                raise MissionCheckpointIntegrityError(
                    f"Mission ID mismatch at sequence {idx}: expected '{mission_id}', got '{file_m_id}'."
                )

            seq = raw_data.get("sequence")
            if seq != idx:
                raise MissionCheckpointIntegrityError(
                    f"Sequence gap at sequence {idx}: expected {idx}, got {seq}."
                )

            c_id = raw_data.get("checkpoint_id")
            if not c_id or c_id in seen_ids:
                raise MissionCheckpointIntegrityError(
                    f"Duplicate or invalid checkpoint ID '{c_id}' at sequence {idx}."
                )
            seen_ids.add(c_id)

            prev_h = raw_data.get("previous_checkpoint_hash")
            if prev_h != previous_hash:
                raise MissionCheckpointIntegrityError(
                    f"Previous checkpoint hash mismatch at sequence {idx}: expected '{previous_hash}', got '{prev_h}'."
                )

            state_snap = raw_data.get("state_snapshot")
            if not isinstance(state_snap, dict):
                raise MissionCheckpointIntegrityError(
                    f"Missing or invalid state_snapshot at sequence {idx}."
                )

            calc_state_hash, calc_snapshot_size = compute_state_hash(state_snap)
            if raw_data.get("state_hash") != calc_state_hash:
                raise MissionCheckpointIntegrityError(
                    f"State hash mismatch at sequence {idx}: expected '{calc_state_hash}', got '{raw_data.get('state_hash')}'."
                )

            created_at_val = raw_data.get("created_at")
            if isinstance(created_at_val, str):
                try:
                    dt = datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except Exception as exc:
                    raise MissionCheckpointIntegrityError(
                        f"Invalid timestamp at sequence {idx}: {exc}"
                    ) from exc
            else:
                raise MissionCheckpointIntegrityError(
                    f"Missing created_at timestamp at sequence {idx}."
                )

            st_iso = dt.astimezone(timezone.utc).isoformat()

            calc_c_hash = compute_canonical_checkpoint_hash(
                schema_version=raw_data.get("schema_version", 1),
                checkpoint_id=c_id,
                mission_id=mission_id,
                sequence=seq,
                created_at_iso=st_iso,
                reason=raw_data.get("reason", "system"),
                status_at_checkpoint=raw_data.get("status_at_checkpoint", "ready"),
                resume_target_status=raw_data.get("resume_target_status"),
                current_task_id=raw_data.get("current_task_id"),
                pending_approval_ids=raw_data.get("pending_approval_ids") or [],
                state_version=raw_data.get("state_version", 0),
                state_hash=calc_state_hash,
                snapshot_size_bytes=calc_snapshot_size,
                resumable=bool(raw_data.get("resumable", False)),
                previous_checkpoint_hash=previous_hash,
            )

            file_c_hash = raw_data.get("checkpoint_hash")
            if file_c_hash != calc_c_hash:
                raise MissionCheckpointIntegrityError(
                    f"Checkpoint hash mismatch at sequence {idx}: expected '{calc_c_hash}', got '{file_c_hash}'."
                )

            rec = MissionCheckpointRecord(
                schema_version=raw_data.get("schema_version", 1),
                checkpoint_id=c_id,
                mission_id=mission_id,
                sequence=seq,
                created_at=dt,
                reason=raw_data.get("reason", "system"),
                status_at_checkpoint=raw_data.get("status_at_checkpoint", "ready"),
                resume_target_status=raw_data.get("resume_target_status"),
                current_task_id=raw_data.get("current_task_id"),
                pending_approval_ids=raw_data.get("pending_approval_ids") or [],
                state_version=raw_data.get("state_version", 0),
                state_hash=calc_state_hash,
                snapshot_size_bytes=calc_snapshot_size,
                resumable=bool(raw_data.get("resumable", False)),
                consumed_by_resume=bool(raw_data.get("consumed_by_resume", False)),
                previous_checkpoint_hash=previous_hash,
                checkpoint_hash=calc_c_hash,
            )

            previous_hash = calc_c_hash
            results.append((rec, state_snap))

        return results

    def _read_and_verify_memory_records(
        self,
        mission_id: str,
    ) -> list[tuple[MissionCheckpointRecord, dict[str, Any]]]:
        if mission_id not in self._memory_store:
            return []

        raw_list = self._memory_store[mission_id]
        results: list[tuple[MissionCheckpointRecord, dict[str, Any]]] = []
        previous_hash: str | None = None
        seen_ids: set[str] = set()

        for idx, raw_data in enumerate(raw_list, start=1):
            file_m_id = raw_data.get("mission_id")
            if file_m_id != mission_id:
                raise MissionCheckpointIntegrityError(
                    f"Mission ID mismatch at sequence {idx}."
                )

            seq = raw_data.get("sequence")
            if seq != idx:
                raise MissionCheckpointIntegrityError(
                    f"Sequence gap at sequence {idx}."
                )

            c_id = raw_data.get("checkpoint_id")
            if not c_id or c_id in seen_ids:
                raise MissionCheckpointIntegrityError(
                    f"Duplicate checkpoint ID '{c_id}' at sequence {idx}."
                )
            seen_ids.add(c_id)

            prev_h = raw_data.get("previous_checkpoint_hash")
            if prev_h != previous_hash:
                raise MissionCheckpointIntegrityError(
                    f"Previous checkpoint hash mismatch at sequence {idx}."
                )

            state_snap = raw_data.get("state_snapshot")
            if not isinstance(state_snap, dict):
                raise MissionCheckpointIntegrityError(
                    f"Missing state_snapshot at sequence {idx}."
                )

            calc_state_hash, calc_snapshot_size = compute_state_hash(state_snap)
            if raw_data.get("state_hash") != calc_state_hash:
                raise MissionCheckpointIntegrityError(
                    f"State hash mismatch at sequence {idx}."
                )

            dt = raw_data.get("created_at")
            if not isinstance(dt, datetime):
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                else:
                    dt = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            st_iso = dt.astimezone(timezone.utc).isoformat()

            calc_c_hash = compute_canonical_checkpoint_hash(
                schema_version=raw_data.get("schema_version", 1),
                checkpoint_id=c_id,
                mission_id=mission_id,
                sequence=seq,
                created_at_iso=st_iso,
                reason=raw_data.get("reason", "system"),
                status_at_checkpoint=raw_data.get("status_at_checkpoint", "ready"),
                resume_target_status=raw_data.get("resume_target_status"),
                current_task_id=raw_data.get("current_task_id"),
                pending_approval_ids=raw_data.get("pending_approval_ids") or [],
                state_version=raw_data.get("state_version", 0),
                state_hash=calc_state_hash,
                snapshot_size_bytes=calc_snapshot_size,
                resumable=bool(raw_data.get("resumable", False)),
                previous_checkpoint_hash=previous_hash,
            )

            file_c_hash = raw_data.get("checkpoint_hash")
            if file_c_hash != calc_c_hash:
                raise MissionCheckpointIntegrityError(
                    f"Checkpoint hash mismatch at sequence {idx}."
                )

            rec = MissionCheckpointRecord(
                schema_version=raw_data.get("schema_version", 1),
                checkpoint_id=c_id,
                mission_id=mission_id,
                sequence=seq,
                created_at=dt,
                reason=raw_data.get("reason", "system"),
                status_at_checkpoint=raw_data.get("status_at_checkpoint", "ready"),
                resume_target_status=raw_data.get("resume_target_status"),
                current_task_id=raw_data.get("current_task_id"),
                pending_approval_ids=raw_data.get("pending_approval_ids") or [],
                state_version=raw_data.get("state_version", 0),
                state_hash=calc_state_hash,
                snapshot_size_bytes=calc_snapshot_size,
                resumable=bool(raw_data.get("resumable", False)),
                consumed_by_resume=bool(raw_data.get("consumed_by_resume", False)),
                previous_checkpoint_hash=previous_hash,
                checkpoint_hash=calc_c_hash,
            )

            previous_hash = calc_c_hash
            results.append((rec, state_snap))

        return results

    def _get_verified_records(
        self,
        mission_id: str,
    ) -> list[tuple[MissionCheckpointRecord, dict[str, Any]]]:
        if self.persistence_enabled and self.root is not None:
            return self._read_and_verify_disk_records(mission_id)
        return self._read_and_verify_memory_records(mission_id)

    def append(
        self,
        *,
        mission_id: str,
        reason: str,
        created_at: datetime,
        status_at_checkpoint: str,
        resume_target_status: str | None,
        current_task_id: str | None,
        pending_approval_ids: Sequence[str] | None,
        state_version: int,
        state_snapshot: Mapping[str, Any],
        resumable: bool,
        checkpoint_id: str | None = None,
    ) -> MissionCheckpointRecord:
        lock = self._get_lock(mission_id)
        with lock:
            verified = self._get_verified_records(mission_id)
            existing_records = [r for r, _ in verified]

            c_id = (checkpoint_id or uuid.uuid4().hex).strip()
            if any(r.checkpoint_id == c_id for r in existing_records):
                raise DuplicateMissionCheckpointError(
                    f"Duplicate checkpoint ID '{c_id}' for mission '{mission_id}'."
                )

            seq = len(existing_records) + 1
            prev_hash = existing_records[-1].checkpoint_hash if existing_records else None

            calc_state_hash, calc_snapshot_size = compute_state_hash(state_snapshot)

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            created_at_iso = created_at.astimezone(timezone.utc).isoformat()

            clean_apps = []
            if pending_approval_ids:
                seen = set()
                for item in pending_approval_ids:
                    if item and item not in seen:
                        seen.add(item)
                        clean_apps.append(item)

            c_hash = compute_canonical_checkpoint_hash(
                schema_version=1,
                checkpoint_id=c_id,
                mission_id=mission_id,
                sequence=seq,
                created_at_iso=created_at_iso,
                reason=reason,
                status_at_checkpoint=status_at_checkpoint,
                resume_target_status=resume_target_status,
                current_task_id=current_task_id,
                pending_approval_ids=clean_apps,
                state_version=state_version,
                state_hash=calc_state_hash,
                snapshot_size_bytes=calc_snapshot_size,
                resumable=resumable,
                previous_checkpoint_hash=prev_hash,
            )

            rec = MissionCheckpointRecord(
                schema_version=1,
                checkpoint_id=c_id,
                mission_id=mission_id,
                sequence=seq,
                created_at=created_at,
                reason=reason,  # type: ignore
                status_at_checkpoint=status_at_checkpoint,
                resume_target_status=resume_target_status,
                current_task_id=current_task_id,
                pending_approval_ids=clean_apps,
                state_version=state_version,
                state_hash=calc_state_hash,
                snapshot_size_bytes=calc_snapshot_size,
                resumable=resumable,
                consumed_by_resume=False,
                previous_checkpoint_hash=prev_hash,
                checkpoint_hash=c_hash,
            )

            file_payload = {
                "schema_version": 1,
                "checkpoint_id": c_id,
                "mission_id": mission_id,
                "sequence": seq,
                "created_at": created_at_iso,
                "reason": reason,
                "status_at_checkpoint": status_at_checkpoint,
                "resume_target_status": resume_target_status,
                "current_task_id": current_task_id,
                "pending_approval_ids": clean_apps,
                "state_version": state_version,
                "state_hash": calc_state_hash,
                "snapshot_size_bytes": calc_snapshot_size,
                "resumable": resumable,
                "previous_checkpoint_hash": prev_hash,
                "checkpoint_hash": c_hash,
                "state_snapshot": dict(state_snapshot),
            }

            path = self._checkpoint_file_path(mission_id)
            if path is not None:
                json_line = json.dumps(
                    file_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ) + "\n"
                with open(path, "ab") as f:
                    f.write(json_line.encode("utf-8"))
                    f.flush()
                    os.fsync(f.fileno())
            else:
                if mission_id not in self._memory_store:
                    self._memory_store[mission_id] = []
                self._memory_store[mission_id].append(file_payload)

            return rec

    def list_checkpoints(
        self,
        *,
        mission_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[MissionCheckpointRecord]:
        lock = self._get_lock(mission_id)
        with lock:
            verified = self._get_verified_records(mission_id)
            records = [r for r, _ in verified if r.sequence > after_sequence]
            return records[:limit]

    def get_checkpoint(
        self,
        *,
        mission_id: str,
        checkpoint_id: str,
    ) -> MissionCheckpointRecord | None:
        lock = self._get_lock(mission_id)
        with lock:
            verified = self._get_verified_records(mission_id)
            for r, _ in verified:
                if r.checkpoint_id == checkpoint_id:
                    return r
            return None

    def get_checkpoint_snapshot(
        self,
        *,
        mission_id: str,
        checkpoint_id: str,
    ) -> dict[str, Any] | None:
        lock = self._get_lock(mission_id)
        with lock:
            verified = self._get_verified_records(mission_id)
            for r, snap in verified:
                if r.checkpoint_id == checkpoint_id:
                    return dict(snap)
            return None

    def verify(
        self,
        *,
        mission_id: str,
    ) -> MissionCheckpointIntegrity:
        lock = self._get_lock(mission_id)
        with lock:
            try:
                verified = self._get_verified_records(mission_id)
                records = [r for r, _ in verified]
                last_seq = records[-1].sequence if records else 0
                last_hash = records[-1].checkpoint_hash if records else None
                return MissionCheckpointIntegrity(
                    mission_id=mission_id,
                    valid=True,
                    checkpoint_count=len(records),
                    last_sequence=last_seq,
                    last_checkpoint_hash=last_hash,
                )
            except MissionCheckpointIntegrityError as exc:
                return MissionCheckpointIntegrity(
                    mission_id=mission_id,
                    valid=False,
                    checkpoint_count=0,
                    last_sequence=0,
                    last_checkpoint_hash=None,
                    error_code=type(exc).__name__,
                )
