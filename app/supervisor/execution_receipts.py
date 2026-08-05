from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping, Literal
import uuid

from app.supervisor.models import (
    ExecutionReceipt,
    ExecutionReceiptIntegrity,
)


class ExecutionReceiptError(RuntimeError):
    pass


class ExecutionReceiptIntegrityError(ExecutionReceiptError):
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


class DuplicateExecutionReceiptError(ExecutionReceiptError):
    pass


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


def sanitize_receipt_data(
    val: Any,
    depth: int = 0,
    max_depth: int = 8,
    project_root: Path | None = None,
) -> Any:
    if depth > max_depth:
        return "[MAX_DEPTH_EXCEEDED]"

    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val

    if isinstance(val, str):
        s = val
        if project_root and str(project_root) in s:
            try:
                rel = Path(s).relative_to(project_root).as_posix()
                s = rel
            except Exception:
                s = s.replace(str(project_root), "[PROJECT_ROOT]")
        elif len(val) < 500:
            try:
                p = Path(val)
                if p.is_absolute():
                    s = "[REDACTED_PATH]"
            except Exception:
                pass

        if "://" in s and "@" in s:
            parts = s.split("://", 1)
            scheme = parts[0]
            rest = parts[1]
            if "@" in rest:
                _, hostpath = rest.split("@", 1)
                s = f"{scheme}://[REDACTED]@{hostpath}"

        if len(s) > 20000:
            return s[:19985] + "...[TRUNCATED]"
        return s

    if isinstance(val, (bytes, bytearray)):
        return f"[BYTES:{len(val)}]"

    if isinstance(val, Path):
        if project_root:
            try:
                return val.relative_to(project_root).as_posix()
            except Exception:
                pass
        return "[REDACTED_PATH]"

    if isinstance(val, Exception):
        return f"[EXCEPTION:{type(val).__name__}]"

    if isinstance(val, Mapping):
        clean_dict: dict[str, Any] = {}
        items_count = 0
        for k, v in val.items():
            if items_count >= 200:
                break
            key_str = str(k)
            key_lower = key_str.lower()
            if any(secret_kw in key_lower for secret_kw in SECRET_DENYLIST):
                clean_dict[key_str] = "[REDACTED]"
            else:
                clean_dict[key_str] = sanitize_receipt_data(
                    v, depth=depth + 1, max_depth=max_depth, project_root=project_root
                )
            items_count += 1
        return clean_dict

    if isinstance(val, (list, tuple, set)):
        clean_list: list[Any] = []
        for item in list(val)[:200]:
            clean_list.append(
                sanitize_receipt_data(
                    item, depth=depth + 1, max_depth=max_depth, project_root=project_root
                )
            )
        return clean_list

    return f"[UNSUPPORTED:{type(val).__name__}]"


def compute_canonical_receipt_hash(
    *,
    schema_version: int,
    receipt_id: str,
    mission_id: str,
    sequence: int,
    execution_kind: str,
    actor_kind: str,
    actor_id: str,
    tool_name: str | None,
    worker_role: str | None,
    task_id: str | None,
    step_id: str | None,
    approval_id: str | None,
    sandbox_id: str | None,
    started_at_iso: str,
    completed_at_iso: str,
    duration_ms: int,
    outcome: str,
    request_summary: str,
    input_hash: str,
    result_hash: str,
    capabilities: list[str],
    filesystem_scope: list[str],
    network_access: list[str],
    exit_code: int | None,
    affected_files: list[str],
    stdout_preview: str | None,
    stderr_preview: str | None,
    artifact_ids: list[str],
    error_code: str | None,
    error_message: str | None,
    metadata: dict[str, Any],
    previous_receipt_hash: str | None,
) -> str:
    canonical_dict = {
        "schema_version": schema_version,
        "receipt_id": receipt_id,
        "mission_id": mission_id,
        "sequence": sequence,
        "execution_kind": execution_kind,
        "actor_kind": actor_kind,
        "actor_id": actor_id,
        "tool_name": tool_name,
        "worker_role": worker_role,
        "task_id": task_id,
        "step_id": step_id,
        "approval_id": approval_id,
        "sandbox_id": sandbox_id,
        "started_at": started_at_iso,
        "completed_at": completed_at_iso,
        "duration_ms": duration_ms,
        "outcome": outcome,
        "request_summary": request_summary,
        "input_hash": input_hash,
        "result_hash": result_hash,
        "capabilities": sorted(capabilities),
        "filesystem_scope": sorted(filesystem_scope),
        "network_access": sorted(network_access),
        "exit_code": exit_code,
        "affected_files": sorted(affected_files),
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
        "artifact_ids": sorted(artifact_ids),
        "error_code": error_code,
        "error_message": error_message,
        "metadata": metadata,
        "previous_receipt_hash": previous_receipt_hash,
    }
    canonical_bytes = json.dumps(
        canonical_dict,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


class ExecutionReceiptStore:
    def __init__(self, *, root: Path | None, persistence_enabled: bool) -> None:
        self.persistence_enabled = bool(persistence_enabled and root is not None)
        self.root = root.resolve() if (root and self.persistence_enabled) else None
        if self.root and self.persistence_enabled:
            self.receipts_dir = self.root / "execution_receipts"
            self.receipts_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.receipts_dir = None

        self._in_memory_receipts: dict[str, list[ExecutionReceipt]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, mission_id: str) -> threading.Lock:
        with self._global_lock:
            lock = self._locks.get(mission_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[mission_id] = lock
            return lock

    def _receipt_file_path(self, mission_id: str) -> Path | None:
        if not self.persistence_enabled or not self.receipts_dir:
            return None
        hashed_id = hashlib.sha256(mission_id.encode("utf-8")).hexdigest()
        return self.receipts_dir / f"{hashed_id}.jsonl"

    def has_receipts(self, *, mission_id: str) -> bool:
        if not mission_id:
            return False
        if not self.persistence_enabled or not self.receipts_dir:
            return mission_id in self._in_memory_receipts and bool(self._in_memory_receipts[mission_id])
        path = self._receipt_file_path(mission_id)
        return path is not None and path.is_file() and path.stat().st_size > 0

    def _read_and_verify_disk_receipts(self, mission_id: str) -> list[ExecutionReceipt]:
        path = self._receipt_file_path(mission_id)
        if not path or not path.is_file():
            return []

        try:
            raw_bytes = path.read_bytes()
        except Exception as exc:
            raise ExecutionReceiptIntegrityError(
                f"Failed to read receipt file for mission '{mission_id}': {exc}",
                error_code="receipt_invalid_utf8",
            ) from exc

        if not raw_bytes:
            return []

        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExecutionReceiptIntegrityError(
                f"Invalid UTF-8 in receipt file for mission '{mission_id}': {exc}",
                error_code="receipt_invalid_utf8",
            ) from exc

        lines = content.splitlines()

        if content and not content.endswith("\n"):
            raise ExecutionReceiptIntegrityError(
                f"Trailing incomplete line in receipt file for mission '{mission_id}'.",
                error_code="receipt_invalid_json",
                error_sequence=len(lines),
            )

        receipts: list[ExecutionReceipt] = []
        seen_ids: set[str] = set()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                data = json.loads(stripped)
            except Exception as exc:
                raise ExecutionReceiptIntegrityError(
                    f"Invalid JSON at record {idx} for mission '{mission_id}': {exc}",
                    error_code="receipt_invalid_json",
                    error_sequence=idx,
                ) from exc

            if not isinstance(data, dict):
                raise ExecutionReceiptIntegrityError(
                    f"Record at sequence {idx} is not a JSON object.",
                    error_code="receipt_invalid_record",
                    error_sequence=idx,
                )

            if data.get("mission_id") != mission_id:
                raise ExecutionReceiptIntegrityError(
                    f"Mission ID mismatch at sequence {idx}: expected '{mission_id}', got '{data.get('mission_id')}'",
                    error_code="receipt_mission_mismatch",
                    error_sequence=idx,
                )

            if data.get("sequence") != idx:
                raise ExecutionReceiptIntegrityError(
                    f"Sequence gap at record {idx}: expected {idx}, got {data.get('sequence')}",
                    error_code="receipt_sequence_gap",
                    error_sequence=idx,
                )

            r_id = data.get("receipt_id")
            if isinstance(r_id, str) and r_id in seen_ids:
                raise ExecutionReceiptIntegrityError(
                    f"Duplicate receipt ID '{r_id}' at sequence {idx}",
                    error_code="receipt_duplicate_id",
                    error_sequence=idx,
                )
            if isinstance(r_id, str):
                seen_ids.add(r_id)

            try:
                rec = ExecutionReceipt.model_validate(data)
            except Exception as exc:
                raise ExecutionReceiptIntegrityError(
                    f"Invalid receipt model at sequence {idx}: {exc}",
                    error_code="receipt_invalid_record",
                    error_sequence=idx,
                ) from exc

            expected_prev_hash = receipts[-1].receipt_hash if receipts else None
            if rec.previous_receipt_hash != expected_prev_hash:
                raise ExecutionReceiptIntegrityError(
                    f"Previous receipt hash mismatch at sequence {idx}: expected '{expected_prev_hash}', got '{rec.previous_receipt_hash}'",
                    error_code="receipt_previous_hash_mismatch",
                    error_sequence=idx,
                )

            st_iso = rec.started_at.astimezone(timezone.utc).isoformat()
            ct_iso = rec.completed_at.astimezone(timezone.utc).isoformat()

            expected_hash = compute_canonical_receipt_hash(
                schema_version=rec.schema_version,
                receipt_id=rec.receipt_id,
                mission_id=rec.mission_id,
                sequence=rec.sequence,
                execution_kind=rec.execution_kind,
                actor_kind=rec.actor_kind,
                actor_id=rec.actor_id,
                tool_name=rec.tool_name,
                worker_role=rec.worker_role,
                task_id=rec.task_id,
                step_id=rec.step_id,
                approval_id=rec.approval_id,
                sandbox_id=rec.sandbox_id,
                started_at_iso=st_iso,
                completed_at_iso=ct_iso,
                duration_ms=rec.duration_ms,
                outcome=rec.outcome,
                request_summary=rec.request_summary,
                input_hash=rec.input_hash,
                result_hash=rec.result_hash,
                capabilities=rec.capabilities,
                filesystem_scope=rec.filesystem_scope,
                network_access=rec.network_access,
                exit_code=rec.exit_code,
                affected_files=rec.affected_files,
                stdout_preview=rec.stdout_preview,
                stderr_preview=rec.stderr_preview,
                artifact_ids=rec.artifact_ids,
                error_code=rec.error_code,
                error_message=rec.error_message,
                metadata=rec.metadata,
                previous_receipt_hash=rec.previous_receipt_hash,
            )

            if rec.receipt_hash != expected_hash:
                raise ExecutionReceiptIntegrityError(
                    f"Receipt hash mismatch at sequence {idx}: computed '{expected_hash}', stored '{rec.receipt_hash}'",
                    error_code="receipt_hash_mismatch",
                    error_sequence=idx,
                )

            receipts.append(rec)

        return receipts

    def append(
        self,
        *,
        mission_id: str,
        execution_kind: str,
        actor_kind: str,
        actor_id: str,
        started_at: datetime,
        completed_at: datetime,
        outcome: str,
        request_summary: str,
        input_value: Any = None,
        result_value: Any = None,
        receipt_id: str | None = None,
        tool_name: str | None = None,
        worker_role: str | None = None,
        task_id: str | None = None,
        step_id: str | None = None,
        approval_id: str | None = None,
        sandbox_id: str | None = None,
        capabilities: list[str] | None = None,
        filesystem_scope: list[str] | None = None,
        network_access: list[str] | None = None,
        exit_code: int | None = None,
        affected_files: list[str] | None = None,
        stdout_preview: str | None = None,
        stderr_preview: str | None = None,
        artifact_ids: list[str] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionReceipt:
        lock = self._get_lock(mission_id)
        with lock:
            existing = self.list_receipts(mission_id=mission_id, after_sequence=0, limit=100000)

            r_id = receipt_id or uuid.uuid4().hex
            if any(r.receipt_id == r_id for r in existing):
                raise DuplicateExecutionReceiptError(
                    f"Duplicate receipt ID '{r_id}' for mission '{mission_id}'."
                )

            seq = len(existing) + 1
            prev_hash = existing[-1].receipt_hash if existing else None

            clean_input = sanitize_receipt_data(input_value, project_root=self.root)
            clean_result = sanitize_receipt_data(result_value, project_root=self.root)
            clean_metadata = sanitize_receipt_data(metadata or {}, project_root=self.root)

            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)

            st_iso = started_at.astimezone(timezone.utc).isoformat()
            ct_iso = completed_at.astimezone(timezone.utc).isoformat()

            dur_ms = int(max(0.0, (completed_at - started_at).total_seconds() * 1000.0))

            input_json = json.dumps(clean_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            input_hash = "sha256:" + hashlib.sha256(input_json.encode("utf-8")).hexdigest()

            result_json = json.dumps(clean_result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            result_hash = "sha256:" + hashlib.sha256(result_json.encode("utf-8")).hexdigest()

            req_sum = str(request_summary or "").strip()[:4000]
            out_prev = str(stdout_preview)[:20000] if stdout_preview is not None else None
            err_prev = str(stderr_preview)[:20000] if stderr_preview is not None else None
            err_msg = str(error_message)[:20000] if error_message is not None else None

            caps = capabilities or []
            fs_scope = filesystem_scope or []
            net_acc = network_access or []
            aff_files = affected_files or []
            art_ids = artifact_ids or []

            rec_hash = compute_canonical_receipt_hash(
                schema_version=1,
                receipt_id=r_id,
                mission_id=mission_id,
                sequence=seq,
                execution_kind=execution_kind,
                actor_kind=actor_kind,
                actor_id=actor_id,
                tool_name=tool_name,
                worker_role=worker_role,
                task_id=task_id,
                step_id=step_id,
                approval_id=approval_id,
                sandbox_id=sandbox_id,
                started_at_iso=st_iso,
                completed_at_iso=ct_iso,
                duration_ms=dur_ms,
                outcome=outcome,
                request_summary=req_sum,
                input_hash=input_hash,
                result_hash=result_hash,
                capabilities=caps,
                filesystem_scope=fs_scope,
                network_access=net_acc,
                exit_code=exit_code,
                affected_files=aff_files,
                stdout_preview=out_prev,
                stderr_preview=err_prev,
                artifact_ids=art_ids,
                error_code=error_code,
                error_message=err_msg,
                metadata=clean_metadata,
                previous_receipt_hash=prev_hash,
            )

            receipt = ExecutionReceipt(
                schema_version=1,
                receipt_id=r_id,
                mission_id=mission_id,
                sequence=seq,
                execution_kind=execution_kind,
                actor_kind=actor_kind,
                actor_id=actor_id,
                tool_name=tool_name,
                worker_role=worker_role,
                task_id=task_id,
                step_id=step_id,
                approval_id=approval_id,
                sandbox_id=sandbox_id,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=dur_ms,
                outcome=outcome,
                request_summary=req_sum,
                input_hash=input_hash,
                result_hash=result_hash,
                capabilities=caps,
                filesystem_scope=fs_scope,
                network_access=net_acc,
                exit_code=exit_code,
                affected_files=aff_files,
                stdout_preview=out_prev,
                stderr_preview=err_prev,
                artifact_ids=art_ids,
                error_code=error_code,
                error_message=err_msg,
                metadata=clean_metadata,
                previous_receipt_hash=prev_hash,
                receipt_hash=rec_hash,
            )

            if not self.persistence_enabled or not self.receipts_dir:
                if mission_id not in self._in_memory_receipts:
                    self._in_memory_receipts[mission_id] = []
                self._in_memory_receipts[mission_id].append(receipt)
                return receipt

            path = self._receipt_file_path(mission_id)
            line_bytes = json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

            try:
                with open(path, "ab") as f:
                    f.write(line_bytes)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as exc:
                raise ExecutionReceiptError(
                    f"Failed to append execution receipt for mission '{mission_id}': {exc}"
                ) from exc

            return receipt

    def list_receipts(
        self,
        *,
        mission_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[ExecutionReceipt]:
        if not self.persistence_enabled or not self.receipts_dir:
            receipts = self._in_memory_receipts.get(mission_id, [])
        else:
            receipts = self._read_and_verify_disk_receipts(mission_id)

        filtered = [r for r in receipts if r.sequence > after_sequence]
        return filtered[:limit]

    def get_receipt(self, *, mission_id: str, receipt_id: str) -> ExecutionReceipt | None:
        receipts = self.list_receipts(mission_id=mission_id, after_sequence=0, limit=100000)
        for r in receipts:
            if r.receipt_id == receipt_id:
                return r
        return None

    def verify(self, *, mission_id: str) -> ExecutionReceiptIntegrity:
        try:
            receipts = self.list_receipts(mission_id=mission_id, after_sequence=0, limit=100000)
            last_seq = receipts[-1].sequence if receipts else 0
            last_hash = receipts[-1].receipt_hash if receipts else None
            return ExecutionReceiptIntegrity(
                mission_id=mission_id,
                valid=True,
                receipt_count=len(receipts),
                last_sequence=last_seq,
                last_receipt_hash=last_hash,
                error_code=None,
                error_sequence=None,
            )
        except ExecutionReceiptIntegrityError as exc:
            return ExecutionReceiptIntegrity(
                mission_id=mission_id,
                valid=False,
                receipt_count=0,
                last_sequence=0,
                last_receipt_hash=None,
                error_code=exc.error_code or "receipt_integrity_failed",
                error_sequence=exc.error_sequence,
            )
