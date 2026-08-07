from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from app.core.exceptions import ToolError
from app.workspace.policy import WorkspacePolicy
from app.workspace.repository_map import REPOSITORY_MAP_REVISION, RepositoryMapSnapshot

SCOPE_LOCK_REVISION = "scope-lock-v1"
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")


class ScopeLockError(ValueError):
    pass


class ScopeLockViolation(ScopeLockError):
    pass


@dataclass(frozen=True)
class ScopeLockSnapshot:
    revision: str
    workspace_path: str
    project_key: str
    repository_map_digest: str
    allowed_write_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    write_path_count: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "repository_map_digest": self.repository_map_digest,
            "allowed_write_paths": list(self.allowed_write_paths),
            "protected_paths": list(self.protected_paths),
            "write_path_count": self.write_path_count,
            "digest": self.digest,
        }


def _digest(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _contains(root: str, path: str) -> bool:
    return path == root or path.startswith(root + "/")


class ScopeLockBuilder:
    def __init__(
        self,
        *,
        project_root: Path,
        workspace_path: str,
        project_key: str,
        max_file_bytes: int = 1_048_576,
        max_search_results: int = 1_000,
    ) -> None:
        raw_root = Path(project_root).expanduser()
        if not raw_root.exists() or not raw_root.is_dir() or raw_root.is_symlink():
            raise ScopeLockError("Scope lock project root is invalid.")
        if not workspace_path or not project_key:
            raise ScopeLockError("Scope lock project identity is invalid.")
        self.project_root = raw_root.resolve()
        self.workspace_path = workspace_path
        self.project_key = project_key
        self.policy = WorkspacePolicy(
            root=self.project_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )

    @classmethod
    def from_runtime(cls, runtime, *, settings) -> "ScopeLockBuilder":
        return cls(
            project_root=runtime.project_root,
            workspace_path=runtime.workspace_path,
            project_key=runtime.project_key,
            max_file_bytes=settings.workspace_max_file_bytes,
            max_search_results=settings.workspace_max_search_results,
        )

    def _normalize(self, value: str, *, writable: bool) -> str:
        if not isinstance(value, str):
            raise ScopeLockError("Scope lock path is invalid.")
        normalized = value.replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized or normalized == "." or normalized.startswith("/") or _DRIVE_PATH.match(normalized):
            raise ScopeLockError("Scope lock path is invalid.")
        parts = normalized.split("/")
        if any(part in {"", "."} for part in parts) or any(part == ".." for part in parts):
            raise ScopeLockError("Scope lock path is invalid.")
        try:
            candidate = self.policy.resolve(normalized, must_exist=False)
            canonical = self.policy.relative(candidate)
        except (ToolError, OSError, ValueError):
            raise ScopeLockError("Scope lock path is invalid.") from None
        if canonical != normalized:
            raise ScopeLockError("Symlinked write paths are not allowed in scope locks.")
        return normalized

    def build(
        self,
        *,
        repository_map: RepositoryMapSnapshot,
        allowed_write_paths: Iterable[str],
        protected_paths: Iterable[str] = (),
    ) -> "ScopeLock":
        _verify_repository_map(repository_map, self.workspace_path, self.project_key)
        if repository_map.truncated or repository_map.depth_truncated:
            raise ScopeLockError("Repository map is incomplete; scope lock cannot be created.")
        canonical_allowed = tuple(sorted({self._normalize(path, writable=True) for path in allowed_write_paths}))
        canonical_protected = tuple(sorted({self._normalize(path, writable=False) for path in protected_paths}))
        map_protected = tuple(sorted(entry.path for entry in repository_map.entries if entry.is_protected_path))
        protected_all = tuple(sorted(set(canonical_protected) | set(map_protected)))
        entries = {entry.path: entry for entry in repository_map.entries}
        for path in canonical_allowed:
            try:
                target = self.policy.resolve(path, must_exist=False)
            except ToolError:
                raise ScopeLockError("Scope lock path is invalid.") from None
            if target.exists() and target.is_dir():
                raise ScopeLockError("Writable scope must contain files, not directories.")
            if any(_contains(root, path) for root in protected_all):
                raise ScopeLockError("Protected repository path cannot be writable.")
            if target.exists() and path not in entries:
                raise ScopeLockError("Existing write target is not present in the repository map.")
        payload: dict[str, object] = {
            "revision": SCOPE_LOCK_REVISION,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "repository_map_digest": repository_map.digest,
            "allowed_write_paths": list(canonical_allowed),
            "protected_paths": list(protected_all),
            "write_path_count": len(canonical_allowed),
        }
        canonical_snapshot_allowed = canonical_allowed
        canonical_snapshot_protected = protected_all
        snapshot = ScopeLockSnapshot(
            revision=SCOPE_LOCK_REVISION,
            workspace_path=self.workspace_path,
            project_key=self.project_key,
            repository_map_digest=repository_map.digest,
            allowed_write_paths=canonical_snapshot_allowed,
            protected_paths=canonical_snapshot_protected,
            write_path_count=len(canonical_snapshot_allowed),
            digest=_digest(payload),
        )
        return ScopeLock(project_root=self.project_root, policy=self.policy, snapshot=snapshot)


def _verify_repository_map(repository_map: RepositoryMapSnapshot, workspace_path: str, project_key: str) -> None:
    try:
        if repository_map.revision != REPOSITORY_MAP_REVISION:
            raise ValueError
        if repository_map.workspace_path != workspace_path or repository_map.project_key != project_key:
            raise ScopeLockError("Repository map does not match the bound project.")
        if repository_map.entry_count != len(repository_map.entries) or repository_map.entry_count > repository_map.max_entries:
            raise ValueError
        paths = [entry.path for entry in repository_map.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError
        for entry in repository_map.entries:
            if not isinstance(entry.path, str) or not entry.path or entry.path.startswith("/") or _DRIVE_PATH.match(entry.path) or "\\" in entry.path:
                raise ValueError
            parts = entry.path.split("/")
            if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(entry.path).as_posix() != entry.path:
                raise ValueError
        payload = repository_map.to_dict()
        digest = payload.pop("digest", None)
        if not isinstance(digest, str) or _digest(payload) != digest:
            raise ValueError
    except ScopeLockError:
        raise
    except Exception:
        raise ScopeLockError("Repository map integrity check failed.") from None


class ScopeLock:
    def __init__(self, *, project_root: Path, policy: WorkspacePolicy, snapshot: ScopeLockSnapshot) -> None:
        self._project_root = project_root
        self._policy = policy
        self._snapshot = snapshot

    @property
    def snapshot(self) -> ScopeLockSnapshot:
        return self._snapshot

    def _normalize_runtime(self, path: str) -> tuple[str, Path]:
        normalized = path.replace("\\", "/").strip() if isinstance(path, str) else ""
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized or normalized == "." or normalized.startswith("/") or _DRIVE_PATH.match(normalized):
            raise ScopeLockViolation("Scope lock rejected the write path.")
        parts = normalized.split("/")
        if any(part in {"", "."} for part in parts) or ".." in parts:
            raise ScopeLockViolation("Scope lock rejected the write path.")
        try:
            candidate = self._policy.resolve(normalized, must_exist=False)
            canonical = self._policy.relative(candidate)
        except (ToolError, OSError, ValueError):
            raise ScopeLockViolation("Scope lock rejected the write path.") from None
        if canonical != normalized:
            raise ScopeLockViolation("Scope lock rejected the write path.")
        return normalized, candidate

    def allows_write(self, path: str) -> bool:
        try:
            self.assert_write(path)
        except ScopeLockViolation:
            return False
        return True

    def assert_write(self, path: str) -> str:
        normalized, candidate = self._normalize_runtime(path)
        if normalized not in self._snapshot.allowed_write_paths:
            raise ScopeLockViolation("Scope lock rejected the write path.")
        if any(_contains(root, normalized) for root in self._snapshot.protected_paths):
            raise ScopeLockViolation("Scope lock rejected the write path.")
        if candidate.exists() and candidate.is_dir():
            raise ScopeLockViolation("Scope lock rejected the write path.")
        return normalized
