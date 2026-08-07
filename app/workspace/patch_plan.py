from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.core.exceptions import ToolError
from app.workspace.policy import WorkspacePolicy
from app.workspace.repository_map import REPOSITORY_MAP_REVISION, RepositoryMapSnapshot
from app.workspace.scope_lock import ScopeLock, ScopeLockViolation

SAFE_PATCH_PLAN_REVISION = "safe-patch-plan-v1"
DEFAULT_MAX_PATCH_OPERATIONS = 128
_DRIVE = re.compile(r"^[A-Za-z]:")


class SafePatchPlanError(ValueError):
    pass


class SafePatchPlanStaleError(SafePatchPlanError):
    pass


class SafePatchPlanMismatch(SafePatchPlanError):
    pass


@dataclass(frozen=True)
class PatchChangeRequest:
    path: str
    operation: str
    replacement_text: str | None = None


@dataclass(frozen=True)
class SafePatchOperationSnapshot:
    path: str
    operation: str
    preimage_state: str
    preimage_sha256: str | None
    preimage_size_bytes: int | None
    replacement_sha256: str | None
    replacement_size_bytes: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "operation": self.operation,
            "preimage_state": self.preimage_state,
            "preimage_sha256": self.preimage_sha256,
            "preimage_size_bytes": self.preimage_size_bytes,
            "replacement_sha256": self.replacement_sha256,
            "replacement_size_bytes": self.replacement_size_bytes,
        }


@dataclass(frozen=True)
class SafePatchPlanSnapshot:
    revision: str
    workspace_path: str
    project_key: str
    repository_map_digest: str
    scope_lock_digest: str
    operations: tuple[SafePatchOperationSnapshot, ...]
    operation_count: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "repository_map_digest": self.repository_map_digest,
            "scope_lock_digest": self.scope_lock_digest,
            "operations": [operation.to_dict() for operation in self.operations],
            "operation_count": self.operation_count,
            "digest": self.digest,
        }


def _digest(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path, limit: int) -> tuple[str, int, int]:
    try:
        before = path.stat()
        if before.st_size > limit:
            raise SafePatchPlanError("Patch target exceeds configured file limit.")
        if not path.is_file() or path.is_symlink():
            raise SafePatchPlanError("Patch target must be a regular file.")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
        after = path.stat()
    except SafePatchPlanError:
        raise
    except OSError:
        raise SafePatchPlanError("Patch target changed during fingerprinting.") from None
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise SafePatchPlanError("Patch target changed during fingerprinting.")
    return "sha256:" + digest.hexdigest(), after.st_size, after.st_mtime_ns


class SafePatchPlanBuilder:
    def __init__(
        self,
        *,
        project_root: Path,
        workspace_path: str,
        project_key: str,
        max_file_bytes: int = 1_048_576,
        max_search_results: int = 1_000,
        max_operations: int = DEFAULT_MAX_PATCH_OPERATIONS,
    ) -> None:
        raw_root = Path(project_root).expanduser()
        if not raw_root.exists() or not raw_root.is_dir() or raw_root.is_symlink():
            raise SafePatchPlanError("Patch plan project root is invalid.")
        if not workspace_path or not project_key or max_file_bytes <= 0:
            raise SafePatchPlanError("Patch plan construction is invalid.")
        if not 1 <= max_operations <= 1024:
            raise SafePatchPlanError("Patch plan operation limit is invalid.")
        self.project_root = raw_root.resolve()
        self.workspace_path = workspace_path
        self.project_key = project_key
        self.max_file_bytes = max_file_bytes
        self.max_operations = max_operations
        self.policy = WorkspacePolicy(root=self.project_root, max_file_bytes=max_file_bytes, max_search_results=max_search_results)

    @classmethod
    def from_runtime(cls, runtime, *, settings, max_operations: int = DEFAULT_MAX_PATCH_OPERATIONS) -> "SafePatchPlanBuilder":
        return cls(
            project_root=runtime.project_root,
            workspace_path=runtime.workspace_path,
            project_key=runtime.project_key,
            max_file_bytes=settings.workspace_max_file_bytes,
            max_search_results=settings.workspace_max_search_results,
            max_operations=max_operations,
        )

    def _path(self, path: str) -> Path:
        if not isinstance(path, str) or not path or path.startswith("/") or _DRIVE.match(path):
            raise SafePatchPlanError("Patch target path is invalid.")
        try:
            return self.policy.resolve(path.replace("\\", "/"), must_exist=False)
        except (ToolError, OSError, ValueError):
            raise SafePatchPlanError("Patch target path is invalid.") from None

    def build(self, *, repository_map: RepositoryMapSnapshot, scope_lock: ScopeLock, changes: Iterable[PatchChangeRequest]) -> "SafePatchPlan":
        _verify_map(repository_map)
        _verify_scope(scope_lock, repository_map)
        if (repository_map.workspace_path, repository_map.project_key) != (self.workspace_path, self.project_key) or (scope_lock.snapshot.workspace_path, scope_lock.snapshot.project_key) != (self.workspace_path, self.project_key):
            raise SafePatchPlanError("Patch plan inputs do not match the bound project.")
        if scope_lock.snapshot.repository_map_digest != repository_map.digest:
            raise SafePatchPlanError("Repository map does not match the scope lock.")
        requests = list(changes)
        if not requests:
            raise SafePatchPlanError("Patch plan must contain at least one operation.")
        if len(requests) > self.max_operations:
            raise SafePatchPlanError("Patch plan exceeds configured operation limit.")
        map_entries = {entry.path for entry in repository_map.entries}
        operations: list[SafePatchOperationSnapshot] = []
        seen: set[str] = set()
        for request in requests:
            if request.operation not in {"create", "replace", "delete"}:
                raise SafePatchPlanError("Patch operation is invalid.")
            try:
                canonical = scope_lock.assert_write(request.path)
            except ScopeLockViolation:
                raise SafePatchPlanError("Patch target is outside the authorized scope.") from None
            if canonical in seen:
                raise SafePatchPlanError("Patch plan contains duplicate target paths.")
            seen.add(canonical)
            target = self._path(canonical)
            exists = target.exists()
            if target.is_symlink():
                raise SafePatchPlanError("Patch target path is invalid.")
            if request.operation == "create":
                if exists:
                    if canonical in map_entries:
                        raise SafePatchPlanError("Patch create target already exists.")
                    raise SafePatchPlanError("Repository state changed since mapping.")
                if canonical in map_entries:
                    raise SafePatchPlanError("Repository state changed since mapping.")
                replacement_hash, replacement_size = _replacement(request.replacement_text, self.max_file_bytes)
                operation = SafePatchOperationSnapshot(canonical, "create", "absent", None, None, replacement_hash, replacement_size)
            else:
                if request.replacement_text is not None and request.operation == "delete":
                    raise SafePatchPlanError("Patch replacement contract is invalid.")
                if request.replacement_text is None and request.operation == "replace":
                    raise SafePatchPlanError("Patch replacement contract is invalid.")
                if not exists:
                    raise SafePatchPlanError("Patch target no longer exists.")
                if target.is_dir() or target.is_symlink():
                    raise SafePatchPlanError("Patch target must be a regular file.")
                if canonical not in map_entries:
                    raise SafePatchPlanError("Existing patch target is not present in the repository map.")
                pre_hash, pre_size, _ = _sha256_file(target, self.max_file_bytes)
                if request.operation == "delete":
                    operation = SafePatchOperationSnapshot(canonical, "delete", "file", pre_hash, pre_size, None, None)
                else:
                    replacement_hash, replacement_size = _replacement(request.replacement_text, self.max_file_bytes)
                    if pre_hash == replacement_hash and pre_size == replacement_size:
                        raise SafePatchPlanError("Patch replacement does not change the target.")
                    operation = SafePatchOperationSnapshot(canonical, "replace", "file", pre_hash, pre_size, replacement_hash, replacement_size)
            operations.append(operation)
        canonical_operations = tuple(sorted(operations, key=lambda item: item.path))
        payload: dict[str, object] = {
            "revision": SAFE_PATCH_PLAN_REVISION,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "repository_map_digest": repository_map.digest,
            "scope_lock_digest": scope_lock.snapshot.digest,
            "operations": [operation.to_dict() for operation in canonical_operations],
            "operation_count": len(canonical_operations),
        }
        snapshot = SafePatchPlanSnapshot(SAFE_PATCH_PLAN_REVISION, self.workspace_path, self.project_key, repository_map.digest, scope_lock.snapshot.digest, canonical_operations, len(canonical_operations), _digest(payload))
        return SafePatchPlan(project_root=self.project_root, policy=self.policy, scope_lock=scope_lock, snapshot=snapshot, max_file_bytes=self.max_file_bytes)


def _replacement(text: str | None, limit: int) -> tuple[str, int]:
    if not isinstance(text, str):
        raise SafePatchPlanError("Patch replacement contract is invalid.")
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError:
        raise SafePatchPlanError("Patch replacement contract is invalid.") from None
    if len(raw) > limit:
        raise SafePatchPlanError("Patch replacement exceeds configured file limit.")
    return "sha256:" + hashlib.sha256(raw).hexdigest(), len(raw)


def _verify_map(repository_map: RepositoryMapSnapshot) -> None:
    try:
        if repository_map.revision != REPOSITORY_MAP_REVISION or repository_map.entry_count != len(repository_map.entries):
            raise ValueError
        paths = [entry.path for entry in repository_map.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError
        payload = repository_map.to_dict(); digest = payload.pop("digest", None)
        if _digest(payload) != digest:
            raise ValueError
        if repository_map.truncated or repository_map.depth_truncated:
            raise SafePatchPlanError("Repository map is incomplete; patch plan cannot be created.")
    except SafePatchPlanError:
        raise
    except Exception:
        raise SafePatchPlanError("Repository map integrity check failed.") from None


def _verify_scope(scope_lock: ScopeLock, repository_map: RepositoryMapSnapshot) -> None:
    try:
        snapshot = scope_lock.snapshot
        if snapshot.revision != "scope-lock-v1" or snapshot.write_path_count != len(snapshot.allowed_write_paths):
            raise ValueError
        if tuple(snapshot.allowed_write_paths) != tuple(sorted(set(snapshot.allowed_write_paths))) or tuple(snapshot.protected_paths) != tuple(sorted(set(snapshot.protected_paths))):
            raise ValueError
        if snapshot.repository_map_digest != repository_map.digest:
            raise SafePatchPlanError("Repository map does not match the scope lock.")
        payload = snapshot.to_dict(); digest = payload.pop("digest", None)
        if _digest(payload) != digest:
            raise ValueError
    except SafePatchPlanError:
        raise
    except Exception:
        raise SafePatchPlanError("Scope lock integrity check failed.") from None


class SafePatchPlan:
    def __init__(self, *, project_root: Path, policy: WorkspacePolicy, scope_lock: ScopeLock, snapshot: SafePatchPlanSnapshot, max_file_bytes: int) -> None:
        self._project_root = project_root
        self._policy = policy
        self._scope_lock = scope_lock
        self._snapshot = snapshot
        self._max_file_bytes = max_file_bytes

    @property
    def snapshot(self) -> SafePatchPlanSnapshot:
        return self._snapshot

    def assert_current(self) -> None:
        for operation in self._snapshot.operations:
            try:
                self._scope_lock.assert_write(operation.path)
            except ScopeLockViolation:
                raise SafePatchPlanStaleError("Patch plan pre-image is stale.") from None
            target = self._policy.resolve(operation.path, must_exist=False)
            if operation.operation == "create":
                if target.exists() or target.is_symlink():
                    raise SafePatchPlanStaleError("Patch plan pre-image is stale.")
                continue
            if not target.exists() or target.is_symlink() or not target.is_file():
                raise SafePatchPlanStaleError("Patch plan pre-image is stale.")
            try:
                current_hash, current_size, _ = _sha256_file(target, self._max_file_bytes)
            except SafePatchPlanError:
                raise SafePatchPlanStaleError("Patch plan pre-image is stale.") from None
            if current_hash != operation.preimage_sha256 or current_size != operation.preimage_size_bytes:
                raise SafePatchPlanStaleError("Patch plan pre-image is stale.")

    def assert_change(self, *, path: str, operation: str, replacement_text: str | None = None) -> SafePatchOperationSnapshot:
        try:
            canonical = self._scope_lock.assert_write(path)
        except ScopeLockViolation:
            raise SafePatchPlanMismatch("Patch change does not match the approved plan.") from None
        match = next((item for item in self._snapshot.operations if item.path == canonical), None)
        if match is None or match.operation != operation:
            raise SafePatchPlanMismatch("Patch change does not match the approved plan.")
        if operation in {"create", "replace"}:
            try:
                replacement_hash, replacement_size = _replacement(replacement_text, self._max_file_bytes)
            except SafePatchPlanError:
                raise SafePatchPlanMismatch("Patch change does not match the approved plan.") from None
            if replacement_hash != match.replacement_sha256 or replacement_size != match.replacement_size_bytes:
                raise SafePatchPlanMismatch("Patch change does not match the approved plan.")
        elif replacement_text is not None:
            raise SafePatchPlanMismatch("Patch change does not match the approved plan.")
        return match
