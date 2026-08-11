"""Durable, explicit human authority for local Git integration."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from app.improvement.post_promotion_verification import SelfDevelopmentPostPromotionVerificationSnapshot

SELF_DEVELOPMENT_GIT_INTEGRATION_APPROVAL_REVISION = "self-development-git-integration-approval-v1"
SELF_DEVELOPMENT_GIT_INTEGRATION_SCOPE = "self-development-local-git-integration"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class SelfDevelopmentGitIntegrationApprovalError(ValueError): pass
class SelfDevelopmentGitIntegrationApprovalValidationError(SelfDevelopmentGitIntegrationApprovalError): pass
class SelfDevelopmentGitIntegrationApprovalIntegrityError(SelfDevelopmentGitIntegrationApprovalError): pass
class SelfDevelopmentGitIntegrationApprovalProjectError(SelfDevelopmentGitIntegrationApprovalError): pass
class SelfDevelopmentGitIntegrationApprovalAuthorizationError(SelfDevelopmentGitIntegrationApprovalError): pass
class SelfDevelopmentGitIntegrationApprovalConflictError(SelfDevelopmentGitIntegrationApprovalError): pass


def _canonical(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SelfDevelopmentGitIntegrationApprovalSnapshot:
    revision: str
    approval_id: str
    workspace_path: str
    project_key: str
    scope: str
    decision: str
    verification_id: str
    verification_digest: str
    execution_id: str
    execution_digest: str
    binding_id: str
    binding_digest: str
    plan_digest: str
    verified_state_digest: str
    source_branch: str
    target_branch: str
    expected_main_sha: str
    local_git_integration_authorized: bool
    remote_publication_authorized: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _payload(snapshot: SelfDevelopmentGitIntegrationApprovalSnapshot, *, include_id: bool = True) -> dict[str, object]:
    value = snapshot.to_dict(); value.pop("digest", None)
    if not include_id: value.pop("approval_id", None)
    return value


def _validate(snapshot: SelfDevelopmentGitIntegrationApprovalSnapshot) -> None:
    if not isinstance(snapshot, SelfDevelopmentGitIntegrationApprovalSnapshot):
        raise SelfDevelopmentGitIntegrationApprovalValidationError("Git integration approval is invalid.")
    if snapshot.revision != SELF_DEVELOPMENT_GIT_INTEGRATION_APPROVAL_REVISION or snapshot.scope != SELF_DEVELOPMENT_GIT_INTEGRATION_SCOPE or snapshot.target_branch != "main":
        raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Git integration approval contract is invalid.")
    if not isinstance(snapshot.approval_id, str) or re.fullmatch(r"sdgia_[0-9a-f]{24}", snapshot.approval_id) is None:
        raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Git integration approval identity is invalid.")
    digests = (snapshot.verification_digest, snapshot.execution_digest, snapshot.binding_digest, snapshot.plan_digest, snapshot.verified_state_digest, snapshot.digest)
    if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in digests) or _GIT_SHA.fullmatch(snapshot.expected_main_sha or "") is None:
        raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Git integration approval digest or baseline is invalid.")
    if snapshot.decision not in {"approve", "reject"} or not all(isinstance(value, str) and value for value in (snapshot.workspace_path, snapshot.project_key, snapshot.verification_id, snapshot.execution_id, snapshot.binding_id, snapshot.source_branch)):
        raise SelfDevelopmentGitIntegrationApprovalValidationError("Git integration approval fields are invalid.")
    if snapshot.source_branch in {"main", "HEAD"} or snapshot.source_branch.startswith("-") or any(ord(ch) < 32 for ch in snapshot.source_branch) or any(token in snapshot.source_branch for token in ("..", "@{", "~", "^", ":")):
        raise SelfDevelopmentGitIntegrationApprovalValidationError("Git integration source branch is invalid.")
    expected_authorized = snapshot.decision == "approve"
    if snapshot.local_git_integration_authorized != expected_authorized or snapshot.remote_publication_authorized:
        raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Git integration approval authorization flags are invalid.")
    if snapshot.approval_id != "sdgia_" + _canonical(_payload(snapshot, include_id=False))[7:31] or _canonical(_payload(snapshot)) != snapshot.digest:
        raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Git integration approval integrity is invalid.")


class SelfDevelopmentGitIntegrationApprovalBuilder:
    def build(self, *, verification: SelfDevelopmentPostPromotionVerificationSnapshot, project_key: str, workspace_path: str, source_branch: str, expected_main_sha: str, decision: str) -> SelfDevelopmentGitIntegrationApprovalSnapshot:
        if not isinstance(verification, SelfDevelopmentPostPromotionVerificationSnapshot):
            raise SelfDevelopmentGitIntegrationApprovalValidationError("Post-promotion verification is invalid.")
        payload = verification.to_dict(); digest = payload.pop("digest")
        if verification.revision != "self-development-post-promotion-verification-v1" or _canonical(payload) != digest or not verification.postimage_verified or not verification.source_state_matches_approved_patch or verification.main_branch_integration_authorized:
            raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Post-promotion verification integrity is invalid.")
        if project_key != verification.project_key or workspace_path != verification.workspace_path:
            raise SelfDevelopmentGitIntegrationApprovalProjectError("Git integration project/workspace does not match verification.")
        if decision not in {"approve", "reject"}:
            raise SelfDevelopmentGitIntegrationApprovalValidationError("Git integration decision is invalid.")
        candidate = SelfDevelopmentGitIntegrationApprovalSnapshot(SELF_DEVELOPMENT_GIT_INTEGRATION_APPROVAL_REVISION, "", workspace_path, project_key, SELF_DEVELOPMENT_GIT_INTEGRATION_SCOPE, decision, verification.verification_id, verification.digest, verification.execution_id, verification.execution_digest, verification.binding_id, verification.binding_digest, verification.plan_digest, verification.verified_state_digest, source_branch, "main", expected_main_sha, decision == "approve", False, "")
        if _GIT_SHA.fullmatch(expected_main_sha or "") is None:
            raise SelfDevelopmentGitIntegrationApprovalValidationError("Expected main baseline must be a full lowercase Git SHA.")
        if not isinstance(source_branch, str) or source_branch in {"main", "HEAD"} or source_branch.startswith("-") or any(ord(ch) < 32 for ch in source_branch) or any(token in source_branch for token in ("..", "@{", "~", "^", ":")):
            raise SelfDevelopmentGitIntegrationApprovalValidationError("Git integration source branch is invalid.")
        approval_id = "sdgia_" + _canonical(_payload(candidate, include_id=False))[7:31]
        candidate = SelfDevelopmentGitIntegrationApprovalSnapshot(**{**candidate.to_dict(), "approval_id": approval_id})
        return SelfDevelopmentGitIntegrationApprovalSnapshot(**{**candidate.to_dict(), "digest": _canonical(_payload(candidate))})


class SelfDevelopmentGitIntegrationApprovalStore:
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.approvals_dir = self.root / "git_integration_approvals"
        self.approvals_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(snapshot: SelfDevelopmentGitIntegrationApprovalSnapshot) -> str:
        return hashlib.sha256((snapshot.verification_id + "\0" + snapshot.verification_digest + "\0" + snapshot.source_branch + "\0" + snapshot.target_branch + "\0" + snapshot.expected_main_sha).encode("utf-8")).hexdigest()

    def _path(self, snapshot: SelfDevelopmentGitIntegrationApprovalSnapshot) -> Path: return self.approvals_dir / (self._key(snapshot) + ".json")

    def _load(self, path: Path) -> SelfDevelopmentGitIntegrationApprovalSnapshot | None:
        if not path.exists(): return None
        try: snapshot = SelfDevelopmentGitIntegrationApprovalSnapshot(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc: raise SelfDevelopmentGitIntegrationApprovalIntegrityError("Persisted Git integration approval is malformed.") from exc
        _validate(snapshot); return snapshot

    def append(self, snapshot: SelfDevelopmentGitIntegrationApprovalSnapshot) -> SelfDevelopmentGitIntegrationApprovalSnapshot:
        _validate(snapshot); path = self._path(snapshot)
        if path.exists():
            existing = self._load(path)
            if existing == snapshot: return existing
            raise SelfDevelopmentGitIntegrationApprovalConflictError("Git integration context already has immutable approval evidence.")
        data = json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            with path.open("xb") as handle: handle.write(data); handle.flush()
        except FileExistsError as exc: raise SelfDevelopmentGitIntegrationApprovalConflictError("Git integration context already has approval evidence.") from exc
        except OSError as exc: raise SelfDevelopmentGitIntegrationApprovalError("Git integration approval persistence failed.") from exc
        return snapshot

    def get_by_verification(self, *, verification_id: str, verification_digest: str) -> SelfDevelopmentGitIntegrationApprovalSnapshot | None:
        if not isinstance(verification_id, str) or not verification_id or not isinstance(verification_digest, str) or _SHA256.fullmatch(verification_digest) is None:
            raise SelfDevelopmentGitIntegrationApprovalValidationError("Git integration approval lookup is invalid.")
        matches = [path for path in self.approvals_dir.glob("*.json") if self._load(path) is not None and self._load(path).verification_id == verification_id and self._load(path).verification_digest == verification_digest]
        return self._load(matches[0]) if matches else None
