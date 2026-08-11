"""Independent, read-only verification of a supervised promotion result."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from app.improvement.approved_patch_binding import SelfDevelopmentApprovedPatchBindingSnapshot
from app.improvement.promotion_execution import SelfDevelopmentPromotionExecutionSnapshot
from app.workspace.patch_approval import SafePatchApprovalBuilder
from app.workspace.patch_plan import SafePatchPlan
from app.workspace.policy import WorkspacePolicy

SELF_DEVELOPMENT_POST_PROMOTION_VERIFICATION_REVISION = "self-development-post-promotion-verification-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class SelfDevelopmentPostPromotionVerificationError(RuntimeError): pass
class SelfDevelopmentPostPromotionVerificationValidationError(SelfDevelopmentPostPromotionVerificationError): pass
class SelfDevelopmentPostPromotionVerificationIntegrityError(SelfDevelopmentPostPromotionVerificationError): pass
class SelfDevelopmentPostPromotionVerificationProjectError(SelfDevelopmentPostPromotionVerificationError): pass
class SelfDevelopmentPostPromotionVerificationAuthorizationError(SelfDevelopmentPostPromotionVerificationError): pass
class SelfDevelopmentPostPromotionVerificationMismatchError(SelfDevelopmentPostPromotionVerificationError): pass
class SelfDevelopmentPostPromotionVerificationConflictError(SelfDevelopmentPostPromotionVerificationError): pass


def _canonical(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest(), len(data)


def _snapshot_payload(snapshot: "SelfDevelopmentPostPromotionVerificationSnapshot", *, include_id: bool = True) -> dict[str, object]:
    payload = snapshot.to_dict()
    payload.pop("digest", None)
    if not include_id:
        payload.pop("verification_id", None)
    return payload


@dataclass(frozen=True)
class SelfDevelopmentPostPromotionVerificationSnapshot:
    revision: str
    verification_id: str
    workspace_path: str
    project_key: str
    execution_id: str
    execution_digest: str
    binding_id: str
    binding_digest: str
    plan_digest: str
    change_payload_digest: str
    promotion_receipt_id: str
    promotion_receipt_digest: str
    verified_state_digest: str
    verified_operation_count: int
    postimage_verified: bool
    source_state_matches_approved_patch: bool
    main_branch_integration_authorized: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _validate_snapshot(snapshot: SelfDevelopmentPostPromotionVerificationSnapshot) -> None:
    if not isinstance(snapshot, SelfDevelopmentPostPromotionVerificationSnapshot):
        raise SelfDevelopmentPostPromotionVerificationValidationError("Post-promotion verification snapshot is invalid.")
    if snapshot.revision != SELF_DEVELOPMENT_POST_PROMOTION_VERIFICATION_REVISION:
        raise SelfDevelopmentPostPromotionVerificationIntegrityError("Post-promotion verification revision is invalid.")
    if not isinstance(snapshot.verification_id, str) or re.fullmatch(r"sdpv_[0-9a-f]{24}", snapshot.verification_id) is None:
        raise SelfDevelopmentPostPromotionVerificationIntegrityError("Post-promotion verification identity is invalid.")
    digests = (snapshot.execution_digest, snapshot.binding_digest, snapshot.plan_digest, snapshot.change_payload_digest, snapshot.promotion_receipt_digest, snapshot.verified_state_digest, snapshot.digest)
    if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in digests):
        raise SelfDevelopmentPostPromotionVerificationIntegrityError("Post-promotion verification digest is invalid.")
    if not all(isinstance(value, str) and value for value in (snapshot.workspace_path, snapshot.project_key, snapshot.execution_id, snapshot.binding_id, snapshot.promotion_receipt_id)):
        raise SelfDevelopmentPostPromotionVerificationValidationError("Post-promotion verification identity fields are invalid.")
    if snapshot.verified_operation_count < 0 or not snapshot.postimage_verified or not snapshot.source_state_matches_approved_patch or snapshot.main_branch_integration_authorized:
        raise SelfDevelopmentPostPromotionVerificationIntegrityError("Post-promotion verification invariants are invalid.")
    if snapshot.verification_id != "sdpv_" + _canonical(_snapshot_payload(snapshot, include_id=False))[7:31] or _canonical(_snapshot_payload(snapshot)) != snapshot.digest:
        raise SelfDevelopmentPostPromotionVerificationIntegrityError("Post-promotion verification snapshot integrity is invalid.")


class SelfDevelopmentPostPromotionVerificationStore:
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.verifications_dir = self.root / "post_promotion_verifications"
        self.verifications_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(execution_id: str, execution_digest: str) -> str:
        return hashlib.sha256((execution_id + "\0" + execution_digest).encode("utf-8")).hexdigest()

    def _path(self, execution_id: str, execution_digest: str) -> Path:
        return self.verifications_dir / (self._key(execution_id, execution_digest) + ".json")

    def _load(self, path: Path) -> SelfDevelopmentPostPromotionVerificationSnapshot | None:
        if not path.exists(): return None
        try:
            snapshot = SelfDevelopmentPostPromotionVerificationSnapshot(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Persisted verification is malformed.") from exc
        _validate_snapshot(snapshot)
        return snapshot

    def append(self, snapshot: SelfDevelopmentPostPromotionVerificationSnapshot) -> SelfDevelopmentPostPromotionVerificationSnapshot:
        _validate_snapshot(snapshot)
        path = self._path(snapshot.execution_id, snapshot.execution_digest)
        if path.exists():
            existing = self._load(path)
            if existing == snapshot: return existing
            raise SelfDevelopmentPostPromotionVerificationConflictError("Execution already has different verification evidence.")
        data = json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            with path.open("xb") as handle:
                handle.write(data); handle.flush()
        except FileExistsError as exc:
            raise SelfDevelopmentPostPromotionVerificationConflictError("Execution already has verification evidence.") from exc
        except OSError as exc:
            raise SelfDevelopmentPostPromotionVerificationError("Verification persistence failed.") from exc
        return snapshot

    def get_by_execution(self, *, execution_id: str, execution_digest: str) -> SelfDevelopmentPostPromotionVerificationSnapshot | None:
        if not isinstance(execution_id, str) or not execution_id or not isinstance(execution_digest, str) or _SHA256.fullmatch(execution_digest) is None:
            raise SelfDevelopmentPostPromotionVerificationValidationError("Verification lookup is invalid.")
        return self._load(self._path(execution_id, execution_digest))

    def is_verified(self, *, execution_id: str, execution_digest: str) -> bool:
        return self.get_by_execution(execution_id=execution_id, execution_digest=execution_digest) is not None


class SelfDevelopmentPostPromotionVerifier:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip():
            raise SelfDevelopmentPostPromotionVerificationProjectError("Verification project is invalid.")
        self.project_key = project_key

    def _validate_inputs(self, *, execution: SelfDevelopmentPromotionExecutionSnapshot, binding: SelfDevelopmentApprovedPatchBindingSnapshot, plan: SafePatchPlan) -> None:
        if not isinstance(execution, SelfDevelopmentPromotionExecutionSnapshot):
            raise SelfDevelopmentPostPromotionVerificationValidationError("Execution snapshot is invalid.")
        if execution.revision != "self-development-promotion-execution-v1" or not re.fullmatch(r"sdpe_[0-9a-f]{24}", execution.execution_id or ""):
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Execution snapshot identity is invalid.")
        if not all(isinstance(value, str) and _SHA256.fullmatch(value) for value in (execution.execution_digest if hasattr(execution, "execution_digest") else execution.digest, execution.authority_digest, execution.binding_digest, execution.plan_digest, execution.change_payload_digest, execution.claim_digest, execution.safe_patch_execution_receipt_digest, execution.promotion_receipt_digest, execution.digest)):
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Execution snapshot integrity is invalid.")
        payload = execution.to_dict(); digest = payload.pop("digest")
        if _canonical(payload) != digest or not execution.promotion_executed or not execution.source_mutation_performed or execution.main_branch_mutation_performed:
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Execution snapshot integrity is invalid.")
        if not isinstance(binding, SelfDevelopmentApprovedPatchBindingSnapshot):
            raise SelfDevelopmentPostPromotionVerificationValidationError("Approved patch binding is invalid.")
        if binding.revision != "self-development-approved-patch-binding-v1" or not isinstance(binding.digest, str) or _SHA256.fullmatch(binding.digest) is None:
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Approved patch binding integrity is invalid.")
        binding_payload = binding.to_dict(); binding_digest = binding_payload.pop("digest")
        if _canonical(binding_payload) != binding_digest:
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Approved patch binding integrity is invalid.")
        if binding.authority_id != execution.authority_id or binding.authority_digest != execution.authority_digest or binding.binding_id != execution.binding_id or binding.digest != execution.binding_digest:
            raise SelfDevelopmentPostPromotionVerificationAuthorizationError("Execution and binding do not match.")
        if binding.project_key != self.project_key or execution.project_key != self.project_key or binding.workspace_path != execution.workspace_path:
            raise SelfDevelopmentPostPromotionVerificationProjectError("Verification project binding is invalid.")
        if not isinstance(plan, SafePatchPlan):
            raise SelfDevelopmentPostPromotionVerificationValidationError("Safe Patch plan is invalid.")
        try:
            validator = SafePatchApprovalBuilder(project_root=plan._project_root, workspace_path=execution.workspace_path, project_key=self.project_key)
            validator._validate_plan(plan)
        except Exception as exc:
            raise SelfDevelopmentPostPromotionVerificationIntegrityError("Safe Patch plan integrity is invalid.") from exc
        if plan.snapshot.digest != execution.plan_digest or plan.snapshot.digest != binding.plan_digest:
            raise SelfDevelopmentPostPromotionVerificationAuthorizationError("Execution, binding and plan do not match.")

    def verify(self, *, execution: SelfDevelopmentPromotionExecutionSnapshot, binding: SelfDevelopmentApprovedPatchBindingSnapshot, plan: SafePatchPlan) -> SelfDevelopmentPostPromotionVerificationSnapshot:
        self._validate_inputs(execution=execution, binding=binding, plan=plan)
        policy = WorkspacePolicy(root=plan._project_root, max_file_bytes=1_048_576, max_search_results=1_000)
        observed = []
        for operation in plan.snapshot.operations:
            try:
                target = policy.resolve(operation.path, must_exist=False)
            except Exception as exc:
                raise SelfDevelopmentPostPromotionVerificationMismatchError("Approved postimage path cannot be verified.") from exc
            if operation.operation == "delete":
                if target.exists() or target.is_symlink():
                    raise SelfDevelopmentPostPromotionVerificationMismatchError("Approved deletion was not applied.")
                observed.append({"path": operation.path, "operation": operation.operation, "state": "missing", "digest": None, "size": None})
                continue
            if not target.exists() or target.is_symlink() or not target.is_file():
                raise SelfDevelopmentPostPromotionVerificationMismatchError("Approved postimage is missing.")
            digest, size = _hash_file(target)
            if digest != operation.replacement_sha256 or size != operation.replacement_size_bytes:
                raise SelfDevelopmentPostPromotionVerificationMismatchError("Promoted workspace does not match the approved postimage.")
            observed.append({"path": operation.path, "operation": operation.operation, "state": "file", "digest": digest, "size": size})
        state_digest = _canonical({"revision": "self-development-observed-postimage-state-v1", "operations": sorted(observed, key=lambda item: (str(item["path"]), str(item["operation"])))})
        payload = {"revision": SELF_DEVELOPMENT_POST_PROMOTION_VERIFICATION_REVISION, "workspace_path": execution.workspace_path, "project_key": self.project_key, "execution_id": execution.execution_id, "execution_digest": execution.digest, "binding_id": binding.binding_id, "binding_digest": binding.digest, "plan_digest": plan.snapshot.digest, "change_payload_digest": execution.change_payload_digest, "promotion_receipt_id": execution.promotion_receipt_id, "promotion_receipt_digest": execution.promotion_receipt_digest, "verified_state_digest": state_digest, "verified_operation_count": len(observed), "postimage_verified": True, "source_state_matches_approved_patch": True, "main_branch_integration_authorized": False}
        verification_id = "sdpv_" + _canonical(payload)[7:31]
        full = {**payload, "verification_id": verification_id}
        return SelfDevelopmentPostPromotionVerificationSnapshot(**{**full, "digest": _canonical(full)})
