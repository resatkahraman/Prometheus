from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.core.exceptions import ToolError
from app.workspace.patch_plan import (
    PatchChangeRequest,
    SafePatchPlan,
    SafePatchPlanError,
    SafePatchPlanStaleError,
)
from app.workspace.policy import WorkspacePolicy
from app.workspace.scope_lock import ScopeLockViolation

SAFE_PATCH_EXECUTOR_REVISION = "safe-patch-executor-v1"


class SafePatchExecutionError(RuntimeError):
    pass


class SafePatchExecutionStaleError(SafePatchExecutionError):
    pass


class SafePatchRollbackError(SafePatchExecutionError):
    pass


@dataclass(frozen=True)
class SafePatchExecutionOperationReceipt:
    path: str
    operation: str
    result_state: str
    result_sha256: str | None
    result_size_bytes: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "operation": self.operation,
            "result_state": self.result_state,
            "result_sha256": self.result_sha256,
            "result_size_bytes": self.result_size_bytes,
        }


@dataclass(frozen=True)
class SafePatchExecutionReceipt:
    revision: str
    workspace_path: str
    project_key: str
    plan_digest: str
    scope_lock_digest: str
    operations: tuple[SafePatchExecutionOperationReceipt, ...]
    operation_count: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "plan_digest": self.plan_digest,
            "scope_lock_digest": self.scope_lock_digest,
            "operations": [operation.to_dict() for operation in self.operations],
            "operation_count": self.operation_count,
            "digest": self.digest,
        }


def _digest(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path, limit: int) -> tuple[str, int]:
    try:
        size = path.stat().st_size
        if size > limit or path.is_symlink() or not path.is_file():
            raise SafePatchExecutionError("Patch execution pre-image is stale.")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest(), size
    except SafePatchExecutionError:
        raise
    except OSError:
        raise SafePatchExecutionError("Patch execution pre-image is stale.") from None


def _cleanup(paths: Iterable[Path]) -> bool:
    ok = True
    for path in paths:
        try:
            if path.exists() or path.is_symlink():
                path.unlink()
        except OSError:
            ok = False
    return ok


class SafePatchExecutor:
    def __init__(self, *, project_root: Path, workspace_path: str, project_key: str, max_file_bytes: int = 1_048_576, max_search_results: int = 1_000) -> None:
        root = Path(project_root).expanduser()
        if not root.exists() or not root.is_dir() or root.is_symlink() or not workspace_path or not project_key or max_file_bytes <= 0:
            raise SafePatchExecutionError("Patch executor construction is invalid.")
        self.project_root = root.resolve()
        self.workspace_path = workspace_path
        self.project_key = project_key
        self.max_file_bytes = max_file_bytes
        self.policy = WorkspacePolicy(root=self.project_root, max_file_bytes=max_file_bytes, max_search_results=max_search_results)

    @classmethod
    def from_runtime(cls, runtime, *, settings) -> "SafePatchExecutor":
        return cls(project_root=runtime.project_root, workspace_path=runtime.workspace_path, project_key=runtime.project_key, max_file_bytes=settings.workspace_max_file_bytes, max_search_results=settings.workspace_max_search_results)

    def _target(self, path: str) -> Path:
        try:
            target = self.policy.resolve(path, must_exist=False, for_write=True)
        except (ToolError, OSError, ValueError):
            raise SafePatchExecutionError("Patch execution target is invalid.") from None
        return target

    def execute(self, *, plan: SafePatchPlan, changes: Iterable[PatchChangeRequest]) -> SafePatchExecutionReceipt:
        _verify_plan(plan)
        snapshot = plan.snapshot
        if snapshot.workspace_path != self.workspace_path or snapshot.project_key != self.project_key:
            raise SafePatchExecutionError("Patch execution plan does not match the bound project.")
        payload = list(changes)
        if len(payload) != snapshot.operation_count:
            raise SafePatchExecutionError("Patch execution payload does not exactly match the approved plan.")
        validated: dict[str, PatchChangeRequest] = {}
        try:
            for change in payload:
                canonical = plan.assert_change(path=change.path, operation=change.operation, replacement_text=change.replacement_text).path
                if canonical in validated:
                    raise SafePatchExecutionError("Patch execution payload does not exactly match the approved plan.")
                validated[canonical] = change
        except SafePatchPlanError:
            raise SafePatchExecutionError("Patch execution payload does not exactly match the approved plan.") from None
        if set(validated) != {operation.path for operation in snapshot.operations}:
            raise SafePatchExecutionError("Patch execution payload does not exactly match the approved plan.")
        try:
            plan.assert_current()
        except SafePatchPlanStaleError:
            raise SafePatchExecutionStaleError("Patch execution pre-image is stale.") from None
        stages: dict[str, Path] = {}
        backups: dict[str, Path] = {}
        artifacts: list[Path] = []
        committed: list = []
        try:
            for operation in snapshot.operations:
                target = self._target(operation.path)
                if not target.parent.exists() or not target.parent.is_dir() or target.parent.is_symlink():
                    raise SafePatchExecutionError("Patch target parent directory does not exist.")
                change = validated[operation.path]
                if operation.operation in {"create", "replace"}:
                    raw = (change.replacement_text or "").encode("utf-8")
                    temp = tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".prometheus-patch-", delete=False)
                    stage = Path(temp.name); artifacts.append(stage)
                    with temp:
                        temp.write(raw); temp.flush(); os.fsync(temp.fileno())
                    staged_hash, staged_size = _hash_file(stage, self.max_file_bytes)
                    if staged_hash != operation.replacement_sha256 or staged_size != operation.replacement_size_bytes:
                        raise SafePatchExecutionError("Patch staging verification failed.")
                    if operation.operation == "replace" and target.exists() and not target.is_symlink():
                        try:
                            os.chmod(stage, stat.S_IMODE(target.stat().st_mode))
                        except OSError:
                            pass
                    stages[operation.path] = stage
                if operation.operation in {"replace", "delete"}:
                    if not target.exists() or target.is_symlink():
                        raise SafePatchExecutionStaleError("Patch execution pre-image is stale.")
                    backup_file = tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".prometheus-rollback-", delete=False)
                    backup = Path(backup_file.name); artifacts.append(backup)
                    with target.open("rb") as source, backup_file:
                        while chunk := source.read(64 * 1024):
                            backup_file.write(chunk)
                        backup_file.flush(); os.fsync(backup_file.fileno())
                    backup_hash, backup_size = _hash_file(backup, self.max_file_bytes)
                    if backup_hash != operation.preimage_sha256 or backup_size != operation.preimage_size_bytes:
                        raise SafePatchExecutionStaleError("Patch execution pre-image is stale.")
                    backups[operation.path] = backup
            try:
                plan.assert_current()
            except SafePatchPlanStaleError:
                raise SafePatchExecutionStaleError("Patch execution pre-image is stale.") from None
            for operation in snapshot.operations:
                target = self._target(operation.path)
                if operation.operation == "create":
                    if target.exists() or target.is_symlink():
                        raise SafePatchExecutionStaleError("Patch execution pre-image is stale.")
                    try:
                        os.link(stages[operation.path], target)
                    except FileExistsError:
                        raise SafePatchExecutionStaleError("Patch execution pre-image is stale.") from None
                    except OSError:
                        raise SafePatchExecutionError("Safe create commit is unsupported by this filesystem.") from None
                    stages[operation.path].unlink(); stages.pop(operation.path, None)
                elif operation.operation == "replace":
                    current_hash, current_size = _hash_file(target, self.max_file_bytes)
                    if current_hash != operation.preimage_sha256 or current_size != operation.preimage_size_bytes:
                        raise SafePatchExecutionStaleError("Patch execution pre-image is stale.")
                    os.replace(stages[operation.path], target); stages.pop(operation.path, None)
                else:
                    current_hash, current_size = _hash_file(target, self.max_file_bytes)
                    if current_hash != operation.preimage_sha256 or current_size != operation.preimage_size_bytes:
                        raise SafePatchExecutionStaleError("Patch execution pre-image is stale.")
                    target.unlink()
                committed.append(operation)
                self._verify_result(operation, target)
            for operation in snapshot.operations:
                self._verify_result(operation, self._target(operation.path))
            if not _cleanup(artifacts):
                raise SafePatchExecutionError("Patch execution artifact cleanup failed.")
        except SafePatchExecutionStaleError:
            if committed:
                rollback_ok = self._rollback(committed, stages, backups)
                _cleanup(artifacts)
                if not rollback_ok:
                    raise SafePatchRollbackError("Patch execution failed and rollback was incomplete.") from None
            else:
                _cleanup(artifacts)
            raise
        except Exception as exc:
            rollback_ok = self._rollback(committed, stages, backups) if committed else True
            _cleanup(artifacts)
            if not rollback_ok:
                raise SafePatchRollbackError("Patch execution failed and rollback was incomplete.") from None
            if isinstance(exc, SafePatchExecutionError):
                raise exc
            raise SafePatchExecutionError("Patch execution failed; committed changes were rolled back.") from None
        receipts = tuple(SafePatchExecutionOperationReceipt(op.path, op.operation, "absent" if op.operation == "delete" else "file", None if op.operation == "delete" else op.replacement_sha256, None if op.operation == "delete" else op.replacement_size_bytes) for op in snapshot.operations)
        receipt_payload = {"revision": SAFE_PATCH_EXECUTOR_REVISION, "workspace_path": self.workspace_path, "project_key": self.project_key, "plan_digest": snapshot.digest, "scope_lock_digest": snapshot.scope_lock_digest, "operations": [r.to_dict() for r in receipts], "operation_count": len(receipts)}
        return SafePatchExecutionReceipt(SAFE_PATCH_EXECUTOR_REVISION, self.workspace_path, self.project_key, snapshot.digest, snapshot.scope_lock_digest, receipts, len(receipts), _digest(receipt_payload))

    def _verify_result(self, operation, target: Path) -> None:
        if operation.operation == "delete":
            if target.exists():
                raise SafePatchExecutionError("Patch execution post-condition failed.")
            return
        if not target.exists() or target.is_symlink() or not target.is_file():
            raise SafePatchExecutionError("Patch execution post-condition failed.")
        digest, size = _hash_file(target, self.max_file_bytes)
        if digest != operation.replacement_sha256 or size != operation.replacement_size_bytes:
            raise SafePatchExecutionError("Patch execution post-condition failed.")

    def _rollback(self, committed, stages, backups) -> bool:
        ok = True
        for operation in reversed(committed):
            target = self._target(operation.path)
            try:
                if operation.operation == "create":
                    if target.exists() and _hash_file(target, self.max_file_bytes) == (operation.replacement_sha256, operation.replacement_size_bytes):
                        target.unlink()
                    else:
                        ok = False
                elif operation.operation == "replace":
                    if not target.exists() or _hash_file(target, self.max_file_bytes) != (operation.replacement_sha256, operation.replacement_size_bytes):
                        ok = False
                    else:
                        os.replace(backups[operation.path], target); backups.pop(operation.path, None)
                else:
                    if target.exists():
                        ok = False
                    else:
                        os.link(backups[operation.path], target); backups[operation.path].unlink(); backups.pop(operation.path, None)
            except OSError:
                ok = False
        return ok


def _verify_plan(plan: SafePatchPlan) -> None:
    try:
        snapshot = plan.snapshot
        if snapshot.revision != "safe-patch-plan-v1" or snapshot.operation_count != len(snapshot.operations) or snapshot.operation_count == 0:
            raise ValueError
        paths = [op.path for op in snapshot.operations]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError
        for op in snapshot.operations:
            if op.operation not in {"create", "replace", "delete"}:
                raise ValueError
            if op.operation == "create" and not (op.preimage_state == "absent" and op.preimage_sha256 is None and op.preimage_size_bytes is None and op.replacement_sha256 and op.replacement_size_bytes is not None):
                raise ValueError
            if op.operation == "replace" and not (op.preimage_state == "file" and op.preimage_sha256 and op.preimage_size_bytes is not None and op.replacement_sha256 and op.replacement_size_bytes is not None and op.preimage_sha256 != op.replacement_sha256):
                raise ValueError
            if op.operation == "delete" and not (op.preimage_state == "file" and op.preimage_sha256 and op.preimage_size_bytes is not None and op.replacement_sha256 is None and op.replacement_size_bytes is None):
                raise ValueError
        payload = snapshot.to_dict(); digest = payload.pop("digest", None)
        if _digest(payload) != digest:
            raise ValueError
    except Exception:
        raise SafePatchExecutionError("Safe patch plan integrity check failed.") from None
