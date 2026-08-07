from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.workspace.repository_map import RepositoryMapSnapshot
from app.workspace.scope_lock import ScopeLock, ScopeLockViolation

SELF_DEVELOPMENT_PROPOSAL_REVISION = "self-development-proposal-v1"
SelfDevelopmentProposalKind = Literal["strategy", "prompt_delta", "router_policy", "source_patch"]
SelfDevelopmentEvidenceKind = Literal["experience_episode", "benchmark_run", "execution_receipt"]
_EVIDENCE_KINDS = frozenset({"experience_episode", "benchmark_run", "execution_receipt"})
_PROPOSAL_KINDS = frozenset({"strategy", "prompt_delta", "router_policy", "source_patch"})
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_HOST_PATH = re.compile(r"(?:^[A-Za-z]:[\\/])|(?:^/(?:home|Users|tmp)(?:/|$))")


class SelfDevelopmentProposalError(ValueError):
    pass


class SelfDevelopmentProposalScopeError(SelfDevelopmentProposalError):
    pass


class SelfDevelopmentProposalEvidenceError(SelfDevelopmentProposalError):
    pass


def _digest(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, *, name: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise SelfDevelopmentProposalError(f"Self-development proposal {name} is invalid.")
    result = value.strip()
    if not minimum <= len(result) <= maximum or "\x00" in result:
        raise SelfDevelopmentProposalError(f"Self-development proposal {name} is invalid.")
    if any(_HOST_PATH.search(line) for line in result.splitlines()):
        raise SelfDevelopmentProposalError("Self-development proposal contains an absolute host path.")
    return result


@dataclass(frozen=True)
class SelfDevelopmentEvidenceReference:
    kind: str
    reference_id: str
    digest: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "reference_id": self.reference_id, "digest": self.digest}


@dataclass(frozen=True)
class SelfDevelopmentProposalRequest:
    kind: str
    title: str
    rationale: str
    expected_outcome: str
    evidence: tuple[SelfDevelopmentEvidenceReference, ...]
    target_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelfDevelopmentProposalSnapshot:
    revision: str
    workspace_path: str
    project_key: str
    kind: str
    title: str
    rationale: str
    expected_outcome: str
    evidence: tuple[SelfDevelopmentEvidenceReference, ...]
    evidence_count: int
    target_paths: tuple[str, ...]
    target_path_count: int
    repository_map_digest: str | None
    scope_lock_digest: str | None
    proposal_only: bool
    automatic_execution_allowed: bool
    automatic_promotion_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision, "workspace_path": self.workspace_path, "project_key": self.project_key,
            "kind": self.kind, "title": self.title, "rationale": self.rationale,
            "expected_outcome": self.expected_outcome, "evidence": [item.to_dict() for item in self.evidence],
            "evidence_count": self.evidence_count, "target_paths": list(self.target_paths),
            "target_path_count": self.target_path_count, "repository_map_digest": self.repository_map_digest,
            "scope_lock_digest": self.scope_lock_digest, "proposal_only": self.proposal_only,
            "automatic_execution_allowed": self.automatic_execution_allowed,
            "automatic_promotion_allowed": self.automatic_promotion_allowed,
            "main_branch_mutation_allowed": self.main_branch_mutation_allowed, "digest": self.digest,
        }


class SelfDevelopmentProposalBuilder:
    def __init__(self, *, project_root: Path, workspace_path: str, project_key: str, max_evidence_refs: int = 32, max_target_paths: int = 32) -> None:
        root = Path(project_root).expanduser()
        if not root.exists() or not root.is_dir() or root.is_symlink() or not isinstance(workspace_path, str) or not workspace_path or not isinstance(project_key, str) or not project_key or not 1 <= max_evidence_refs <= 256 or not 1 <= max_target_paths <= 256:
            raise SelfDevelopmentProposalError("Self-development proposal construction is invalid.")
        self._project_root = root.resolve()
        self.workspace_path = workspace_path
        self.project_key = project_key
        self.max_evidence_refs = max_evidence_refs
        self.max_target_paths = max_target_paths

    @classmethod
    def from_runtime(cls, runtime, *, max_evidence_refs: int = 32, max_target_paths: int = 32) -> "SelfDevelopmentProposalBuilder":
        return cls(project_root=runtime.project_root, workspace_path=runtime.workspace_path, project_key=runtime.project_key, max_evidence_refs=max_evidence_refs, max_target_paths=max_target_paths)

    def _evidence(self, values: tuple[SelfDevelopmentEvidenceReference, ...]) -> tuple[SelfDevelopmentEvidenceReference, ...]:
        try:
            items = tuple(values)
        except TypeError:
            raise SelfDevelopmentProposalEvidenceError("Phase-3 self-development proposals require valid evidence references.") from None
        if not items or len(items) > self.max_evidence_refs:
            raise SelfDevelopmentProposalEvidenceError("Phase-3 self-development proposals must be evidence-referenced.")
        seen: set[tuple[str, str, str]] = set()
        for item in items:
            if not isinstance(item, SelfDevelopmentEvidenceReference) or item.kind not in _EVIDENCE_KINDS or not isinstance(item.reference_id, str) or not item.reference_id.strip() or len(item.reference_id.strip()) > 160 or not isinstance(item.digest, str) or not _SHA256.fullmatch(item.digest):
                raise SelfDevelopmentProposalEvidenceError("Self-development evidence reference is invalid.")
            key = (item.kind, item.reference_id.strip(), item.digest)
            if key in seen:
                raise SelfDevelopmentProposalEvidenceError("Self-development evidence references must be unique.")
            seen.add(key)
        return tuple(sorted((SelfDevelopmentEvidenceReference(k, r, d) for k, r, d in seen), key=lambda item: (item.kind, item.reference_id, item.digest)))

    @staticmethod
    def _verify_map(repository_map: RepositoryMapSnapshot, workspace_path: str, project_key: str) -> None:
        try:
            if repository_map.workspace_path != workspace_path or repository_map.project_key != project_key or repository_map.entry_count != len(repository_map.entries) or repository_map.truncated or repository_map.depth_truncated:
                raise ValueError
            paths = [entry.path for entry in repository_map.entries]
            if paths != sorted(paths) or len(paths) != len(set(paths)) or not _SHA256.fullmatch(repository_map.digest):
                raise ValueError
            payload = repository_map.to_dict(); digest = payload.pop("digest")
            if _digest(payload) != digest:
                raise ValueError
        except Exception:
            raise SelfDevelopmentProposalScopeError("Self-development repository map is invalid.") from None

    @staticmethod
    def _verify_scope(scope_lock: ScopeLock, repository_map: RepositoryMapSnapshot, workspace_path: str, project_key: str) -> None:
        try:
            snapshot = scope_lock.snapshot
            if snapshot.workspace_path != workspace_path or snapshot.project_key != project_key or snapshot.repository_map_digest != repository_map.digest or snapshot.write_path_count != len(snapshot.allowed_write_paths) or list(snapshot.allowed_write_paths) != sorted(snapshot.allowed_write_paths) or len(set(snapshot.allowed_write_paths)) != len(snapshot.allowed_write_paths) or not _SHA256.fullmatch(snapshot.digest):
                raise ValueError
            payload = snapshot.to_dict(); digest = payload.pop("digest")
            if _digest(payload) != digest:
                raise ValueError
        except Exception:
            raise SelfDevelopmentProposalScopeError("Self-development scope lock is invalid.") from None

    def build(self, *, request: SelfDevelopmentProposalRequest, repository_map: RepositoryMapSnapshot | None = None, scope_lock: ScopeLock | None = None) -> SelfDevelopmentProposalSnapshot:
        if not isinstance(request, SelfDevelopmentProposalRequest) or request.kind not in _PROPOSAL_KINDS:
            raise SelfDevelopmentProposalError("Self-development proposal kind is invalid.")
        title = _text(request.title, name="title", minimum=3, maximum=160)
        rationale = _text(request.rationale, name="rationale", minimum=10, maximum=4000)
        expected = _text(request.expected_outcome, name="expected outcome", minimum=3, maximum=2000)
        evidence = self._evidence(request.evidence)
        raw_targets = tuple(request.target_paths)
        if request.kind != "source_patch":
            if raw_targets or repository_map is not None or scope_lock is not None:
                raise SelfDevelopmentProposalScopeError("Logical proposals cannot carry source scope.")
            targets: tuple[str, ...] = ()
            map_digest = scope_digest = None
        else:
            if repository_map is None or scope_lock is None or not raw_targets or len(raw_targets) > self.max_target_paths:
                raise SelfDevelopmentProposalScopeError("Source-patch proposals require bounded repository scope.")
            self._verify_map(repository_map, self.workspace_path, self.project_key)
            self._verify_scope(scope_lock, repository_map, self.workspace_path, self.project_key)
            canonical: set[str] = set()
            entries = {entry.path: entry for entry in repository_map.entries}
            for path in raw_targets:
                try:
                    normalized = scope_lock.assert_write(path)
                except (ScopeLockViolation, TypeError, ValueError):
                    raise SelfDevelopmentProposalScopeError("Source-patch target is outside the authorized scope.") from None
                if normalized in canonical or normalized not in entries or entries[normalized].role not in {"source", "test"}:
                    raise SelfDevelopmentProposalScopeError("Source-patch target is outside the authorized scope.")
                canonical.add(normalized)
            targets = tuple(sorted(canonical))
            map_digest, scope_digest = repository_map.digest, scope_lock.snapshot.digest
        payload = {"revision": SELF_DEVELOPMENT_PROPOSAL_REVISION, "workspace_path": self.workspace_path, "project_key": self.project_key, "kind": request.kind, "title": title, "rationale": rationale, "expected_outcome": expected, "evidence": [item.to_dict() for item in evidence], "evidence_count": len(evidence), "target_paths": list(targets), "target_path_count": len(targets), "repository_map_digest": map_digest, "scope_lock_digest": scope_digest, "proposal_only": True, "automatic_execution_allowed": False, "automatic_promotion_allowed": False, "main_branch_mutation_allowed": False}
        return SelfDevelopmentProposalSnapshot(SELF_DEVELOPMENT_PROPOSAL_REVISION, self.workspace_path, self.project_key, request.kind, title, rationale, expected, evidence, len(evidence), targets, len(targets), map_digest, scope_digest, True, False, False, False, _digest(payload))
