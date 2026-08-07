from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from app.core.exceptions import ToolError
from app.workspace.policy import WorkspacePolicy

REPOSITORY_MAP_REVISION = "repository-map-v1"
IGNORED_DIRECTORY_NAMES = (
    ".git", ".hg", ".svn", ".adam", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", "ruff_cache", ".tox",
    ".nox", "dist", "build",
)
_IGNORED = frozenset(IGNORED_DIRECTORY_NAMES)


class RepositoryMapError(ValueError):
    """Safe, stable errors raised while constructing a repository map."""


def classify_repository_path(path: str) -> str:
    parts = tuple(Path(path).parts)
    filename = parts[-1] if parts else ""
    name = filename.casefold()
    components = {part.casefold() for part in parts[:-1]}
    if ({"tests", "test", "__tests__"} & components or name.startswith("test_")):
        return "test"
    if name.endswith("_test.py") or name.endswith((".test.js", ".test.ts", ".test.jsx", ".test.tsx")):
        return "test"
    if name.endswith((".spec.js", ".spec.ts", ".spec.jsx", ".spec.tsx")):
        return "test"
    suffix = Path(name).suffix
    if "docs" in components or suffix in {".md", ".rst"}:
        return "docs"
    config_names = {
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "requirements-dev.txt", "pipfile", "pipfile.lock", "poetry.lock",
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "tsconfig.json", "dockerfile", "docker-compose.yml", "docker-compose.yaml", "makefile",
    }
    if name in config_names or suffix in {".toml", ".yaml", ".yml", ".ini", ".cfg"}:
        return "config"
    if suffix in {
        ".py", ".pyx", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".kts",
        ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift",
        ".scala", ".sh", ".ps1", ".sql", ".html", ".css", ".scss",
    }:
        return "source"
    return "other"


@dataclass(frozen=True)
class RepositoryMapEntry:
    path: str
    role: str
    suffix: str
    size_bytes: int
    depth: int
    is_key_path: bool = False
    is_protected_path: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryMapSnapshot:
    revision: str
    workspace_path: str
    project_key: str
    entries: tuple[RepositoryMapEntry, ...]
    entry_count: int
    max_entries: int
    max_depth: int
    truncated: bool
    depth_truncated: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "entries": [entry.to_dict() for entry in self.entries],
            "entry_count": self.entry_count,
            "max_entries": self.max_entries,
            "max_depth": self.max_depth,
            "truncated": self.truncated,
            "depth_truncated": self.depth_truncated,
            "digest": self.digest,
        }


def _digest_payload(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class RepositoryMapBuilder:
    def __init__(
        self,
        *,
        project_root: Path,
        workspace_path: str,
        project_key: str,
        max_entries: int = 5_000,
        max_depth: int = 20,
        max_path_chars: int = 1_000,
        max_file_bytes: int = 1_048_576,
        max_search_results: int = 1_000,
    ) -> None:
        raw_root = Path(project_root).expanduser()
        if not raw_root.exists() or not raw_root.is_dir() or raw_root.is_symlink():
            raise RepositoryMapError("Repository root is invalid.")
        if not workspace_path or not project_key or Path(workspace_path).is_absolute():
            raise RepositoryMapError("Repository identity is invalid.")
        if max_entries < 1 or max_depth < 1 or max_path_chars < 1:
            raise RepositoryMapError("Repository mapping bounds are invalid.")
        self.project_root = raw_root.resolve()
        self.workspace_path = workspace_path
        self.project_key = project_key
        self.max_entries = max_entries
        self.max_depth = max_depth
        self.max_path_chars = max_path_chars
        self.policy = WorkspacePolicy(root=self.project_root, max_file_bytes=max_file_bytes, max_search_results=max_search_results)

    @classmethod
    def from_runtime(cls, runtime, *, settings) -> "RepositoryMapBuilder":
        return cls(
            project_root=runtime.project_root,
            workspace_path=runtime.workspace_path,
            project_key=runtime.project_key,
            max_entries=settings.repository_map_max_entries,
            max_depth=settings.repository_map_max_depth,
            max_path_chars=settings.repository_map_max_path_chars,
            max_file_bytes=settings.workspace_max_file_bytes,
            max_search_results=settings.workspace_max_search_results,
        )

    def _normalize_paths(self, paths: Iterable[str]) -> tuple[str, ...]:
        normalized: set[str] = set()
        for value in paths:
            try:
                relative = self.policy.relative(self.policy.resolve(value, must_exist=False))
            except (ToolError, OSError, ValueError, TypeError):
                continue
            if relative != "." and len(relative) <= self.max_path_chars:
                normalized.add(relative)
        return tuple(sorted(normalized))

    @staticmethod
    def _under(path: str, roots: tuple[str, ...]) -> bool:
        return any(path == root or path.startswith(root + "/") for root in roots)

    def build(self, *, key_paths: Iterable[str] = (), protected_paths: Iterable[str] = ()) -> RepositoryMapSnapshot:
        keys = self._normalize_paths(key_paths)
        protected = self._normalize_paths(protected_paths)
        entries: list[RepositoryMapEntry] = []
        truncated = False
        depth_truncated = False

        def visit(directory: Path, parts: tuple[str, ...]) -> bool:
            nonlocal truncated, depth_truncated
            try:
                children = sorted(directory.iterdir(), key=lambda item: item.name)
            except OSError:
                raise RepositoryMapError("Repository changed during mapping.") from None
            for child in children:
                if child.is_symlink():
                    continue
                child_parts = parts + (child.name,)
                relative = "/".join(child_parts)
                if len(relative) > self.max_path_chars:
                    raise RepositoryMapError("Repository path exceeds configured mapping limit.")
                try:
                    safe = self.policy.resolve(relative, must_exist=True)
                except ToolError:
                    if not child.exists():
                        raise RepositoryMapError("Repository changed during mapping.") from None
                    continue
                try:
                    if safe.is_dir():
                        if child.name in _IGNORED:
                            continue
                        if len(child_parts) >= self.max_depth:
                            depth_truncated = True
                            continue
                        if not visit(safe, child_parts):
                            return False
                    elif safe.is_file():
                        if len(entries) >= self.max_entries:
                            truncated = True
                            return False
                        try:
                            size = safe.stat().st_size
                        except OSError:
                            raise RepositoryMapError("Repository changed during mapping.") from None
                        entries.append(RepositoryMapEntry(
                            path=relative,
                            role=classify_repository_path(relative),
                            suffix=safe.suffix.casefold(),
                            size_bytes=max(0, size),
                            depth=len(child_parts),
                            is_key_path=self._under(relative, keys),
                            is_protected_path=self._under(relative, protected),
                        ))
                except OSError:
                    raise RepositoryMapError("Repository changed during mapping.") from None
            return True

        visit(self.project_root, ())
        entries.sort(key=lambda entry: entry.path)
        canonical_entries = tuple(entries)
        payload: dict[str, object] = {
            "revision": REPOSITORY_MAP_REVISION,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "entries": [entry.to_dict() for entry in canonical_entries],
            "entry_count": len(canonical_entries),
            "max_entries": self.max_entries,
            "max_depth": self.max_depth,
            "truncated": truncated,
            "depth_truncated": depth_truncated,
        }
        return RepositoryMapSnapshot(
            revision=REPOSITORY_MAP_REVISION,
            workspace_path=self.workspace_path,
            project_key=self.project_key,
            entries=canonical_entries,
            entry_count=len(canonical_entries),
            max_entries=self.max_entries,
            max_depth=self.max_depth,
            truncated=truncated,
            depth_truncated=depth_truncated,
            digest=_digest_payload(payload),
        )
