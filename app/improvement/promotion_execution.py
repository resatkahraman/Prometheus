"""The supervised, claim-before-mutation promotion boundary."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from app.improvement.approved_patch_binding import (
    SelfDevelopmentApprovedPatchBindingSnapshot,
    SelfDevelopmentApprovedPatchBinder,
    SelfDevelopmentApprovedPatchBindingAuthorizationError,
    SelfDevelopmentApprovedPatchBindingProjectError,
    SELF_DEVELOPMENT_APPROVED_PATCH_BINDING_REVISION,
    _binding_payload,
)
from app.improvement.promotion_authority import SelfDevelopmentPromotionAuthoritySnapshot
from app.improvement.promotion_receipts import (
    SelfDevelopmentPromotionExecutionReceipt,
    SelfDevelopmentPromotionReceiptConflictError,
    SelfDevelopmentPromotionReceiptStore,
    _canonical,
    _payload as receipt_payload,
)
from app.workspace.patch_approval import SafePatchApprovalBindingSnapshot
from app.workspace.patch_executor import SafePatchExecutionReceipt, SafePatchExecutor
from app.workspace.patch_plan import PatchChangeRequest, SafePatchPlan

SELF_DEVELOPMENT_PROMOTION_EXECUTION_REVISION = "self-development-promotion-execution-v1"
SELF_DEVELOPMENT_PROMOTION_EXECUTION_CLAIM_REVISION = "self-development-promotion-execution-claim-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class SelfDevelopmentPromotionExecutionError(RuntimeError):
    pass


class SelfDevelopmentPromotionExecutionValidationError(SelfDevelopmentPromotionExecutionError):
    pass


class SelfDevelopmentPromotionExecutionIntegrityError(SelfDevelopmentPromotionExecutionError):
    pass


class SelfDevelopmentPromotionExecutionProjectError(SelfDevelopmentPromotionExecutionError):
    pass


class SelfDevelopmentPromotionExecutionAuthorizationError(SelfDevelopmentPromotionExecutionError):
    pass


class SelfDevelopmentPromotionExecutionReplayError(SelfDevelopmentPromotionExecutionError):
    pass


class SelfDevelopmentPromotionExecutionRecoveryRequiredError(SelfDevelopmentPromotionExecutionError):
    pass


def _digest(value: object) -> str:
    return _canonical(value)


def _change_payload(changes: Iterable[PatchChangeRequest]) -> tuple[dict[str, object], ...]:
    items = []
    for change in changes:
        if not isinstance(change, PatchChangeRequest) or not isinstance(change.path, str) or not isinstance(change.operation, str):
            raise SelfDevelopmentPromotionExecutionValidationError("Promotion change payload is invalid.")
        if change.operation not in {"create", "replace", "delete"} or not change.path:
            raise SelfDevelopmentPromotionExecutionValidationError("Promotion change payload is invalid.")
        if change.operation != "delete" and not isinstance(change.replacement_text, str):
            raise SelfDevelopmentPromotionExecutionValidationError("Promotion change payload is invalid.")
        if change.operation == "delete" and change.replacement_text is not None:
            raise SelfDevelopmentPromotionExecutionValidationError("Promotion change payload is invalid.")
        items.append({"path": change.path, "operation": change.operation, "replacement_text": change.replacement_text})
    ordered = tuple(sorted(items, key=lambda item: str(item["path"])))
    if len({item["path"] for item in ordered}) != len(ordered):
        raise SelfDevelopmentPromotionExecutionValidationError("Promotion change payload is invalid.")
    return ordered


def _payload_digest(changes: Iterable[PatchChangeRequest]) -> str:
    return _digest({"revision": "self-development-promotion-change-payload-v1", "changes": list(_change_payload(changes))})


@dataclass(frozen=True)
class SelfDevelopmentPromotionExecutionClaim:
    revision: str
    claim_id: str
    workspace_path: str
    project_key: str
    authority_id: str
    authority_digest: str
    binding_id: str
    binding_digest: str
    candidate_id: str
    candidate_digest: str
    plan_digest: str
    preview_digest: str
    patch_approval_digest: str
    change_payload_digest: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _claim_payload(claim: SelfDevelopmentPromotionExecutionClaim, *, include_id: bool = True) -> dict[str, object]:
    payload = claim.to_dict()
    payload.pop("digest", None)
    if not include_id:
        payload.pop("claim_id", None)
    return payload


def _validate_claim(claim: SelfDevelopmentPromotionExecutionClaim) -> None:
    if not isinstance(claim, SelfDevelopmentPromotionExecutionClaim):
        raise SelfDevelopmentPromotionExecutionValidationError("Promotion execution claim is invalid.")
    if claim.revision != SELF_DEVELOPMENT_PROMOTION_EXECUTION_CLAIM_REVISION:
        raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion execution claim revision is invalid.")
    values = (claim.authority_digest, claim.binding_digest, claim.candidate_digest, claim.plan_digest, claim.preview_digest, claim.patch_approval_digest, claim.change_payload_digest, claim.digest)
    if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in values):
        raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion execution claim digest is invalid.")
    if not isinstance(claim.claim_id, str) or re.fullmatch(r"sdpc_[0-9a-f]{24}", claim.claim_id) is None:
        raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion execution claim identity is invalid.")
    if not all(isinstance(value, str) and value for value in (claim.workspace_path, claim.project_key, claim.authority_id, claim.binding_id, claim.candidate_id)):
        raise SelfDevelopmentPromotionExecutionValidationError("Promotion execution claim identity fields are invalid.")
    if claim.claim_id != "sdpc_" + _digest(_claim_payload(claim, include_id=False))[7:31] or _digest(_claim_payload(claim)) != claim.digest:
        raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion execution claim integrity is invalid.")


class SelfDevelopmentPromotionExecutionClaimStore:
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.claims_dir = self.root / "promotion_execution_claims"
        self.claims_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(binding_id: str, binding_digest: str) -> str:
        return hashlib.sha256((binding_id + "\0" + binding_digest).encode("utf-8")).hexdigest()

    def _path(self, binding_id: str, binding_digest: str) -> Path:
        return self.claims_dir / (self._key(binding_id, binding_digest) + ".json")

    def _load(self, path: Path) -> SelfDevelopmentPromotionExecutionClaim | None:
        if not path.exists():
            return None
        try:
            claim = SelfDevelopmentPromotionExecutionClaim(**json.loads(path.read_text(encoding="utf-8")))
        except SelfDevelopmentApprovedPatchBindingAuthorizationError as exc:
            raise SelfDevelopmentPromotionExecutionAuthorizationError("Promotion execution approval is not authorized for the supplied plan.") from exc
        except SelfDevelopmentApprovedPatchBindingProjectError as exc:
            raise SelfDevelopmentPromotionExecutionProjectError("Promotion execution project binding is invalid.") from exc
        except Exception as exc:
            raise SelfDevelopmentPromotionExecutionIntegrityError("Persisted promotion execution claim is malformed.") from exc
        _validate_claim(claim)
        return claim

    def claim(self, claim: SelfDevelopmentPromotionExecutionClaim) -> SelfDevelopmentPromotionExecutionClaim:
        _validate_claim(claim)
        path = self._path(claim.binding_id, claim.binding_digest)
        if path.exists():
            self._load(path)
            raise SelfDevelopmentPromotionExecutionRecoveryRequiredError("Promotion execution requires recovery.")
        data = json.dumps(claim.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            with path.open("xb") as handle:
                handle.write(data)
                handle.flush()
        except FileExistsError as exc:
            raise SelfDevelopmentPromotionExecutionRecoveryRequiredError("Promotion execution requires recovery.") from exc
        except OSError as exc:
            raise SelfDevelopmentPromotionExecutionError("Promotion execution claim persistence failed.") from exc
        return claim

    def get_by_binding(self, *, binding_id: str, binding_digest: str) -> SelfDevelopmentPromotionExecutionClaim | None:
        if not isinstance(binding_id, str) or not binding_id or not isinstance(binding_digest, str) or _SHA256.fullmatch(binding_digest) is None:
            raise SelfDevelopmentPromotionExecutionValidationError("Promotion execution claim lookup is invalid.")
        return self._load(self._path(binding_id, binding_digest))

    def is_claimed(self, *, binding_id: str, binding_digest: str) -> bool:
        return self.get_by_binding(binding_id=binding_id, binding_digest=binding_digest) is not None


@dataclass(frozen=True)
class SelfDevelopmentPromotionExecutionSnapshot:
    revision: str
    execution_id: str
    workspace_path: str
    project_key: str
    authority_id: str
    authority_digest: str
    binding_id: str
    binding_digest: str
    candidate_id: str
    candidate_digest: str
    plan_digest: str
    preview_digest: str
    patch_approval_digest: str
    change_payload_digest: str
    claim_id: str
    claim_digest: str
    safe_patch_execution_receipt_id: str
    safe_patch_execution_receipt_digest: str
    promotion_receipt_id: str
    promotion_receipt_digest: str
    promotion_executed: bool
    source_mutation_performed: bool
    main_branch_mutation_performed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class SelfDevelopmentPromotionExecutor:
    def __init__(self, *, project_key: str, safe_patch_executor: SafePatchExecutor, receipt_store: SelfDevelopmentPromotionReceiptStore, claim_store: SelfDevelopmentPromotionExecutionClaimStore) -> None:
        if not isinstance(project_key, str) or not project_key.strip():
            raise SelfDevelopmentPromotionExecutionProjectError("Promotion execution project is invalid.")
        self.project_key = project_key
        self.safe_patch_executor = safe_patch_executor
        self.receipt_store = receipt_store
        self.claim_store = claim_store

    def _validate_chain(self, *, authority: SelfDevelopmentPromotionAuthoritySnapshot, binding: SelfDevelopmentApprovedPatchBindingSnapshot, plan: SafePatchPlan, approval: SafePatchApprovalBindingSnapshot) -> None:
        try:
            SelfDevelopmentApprovedPatchBinder._verify_authority(authority, self.project_key)
            if not isinstance(binding, SelfDevelopmentApprovedPatchBindingSnapshot):
                raise ValueError
            if binding.revision != SELF_DEVELOPMENT_APPROVED_PATCH_BINDING_REVISION or binding.project_key != self.project_key or binding.workspace_path != authority.workspace_path:
                raise ValueError
            if not all(isinstance(value, str) and _SHA256.fullmatch(value) for value in (binding.authority_digest, binding.decision_digest, binding.candidate_digest, binding.plan_digest, binding.preview_digest, binding.patch_approval_digest, binding.digest)):
                raise ValueError
            if binding.authority_id != authority.authority_id or binding.authority_digest != authority.digest:
                raise SelfDevelopmentPromotionExecutionAuthorizationError("Promotion execution authority and binding do not match.")
            expected_id = "sdpb_" + _canonical(_binding_payload(authority=authority, plan_digest=binding.plan_digest, preview_digest=binding.preview_digest, approval_digest=binding.patch_approval_digest))[7:31]
            if binding.binding_id != expected_id or _canonical(_binding_payload(authority=authority, plan_digest=binding.plan_digest, preview_digest=binding.preview_digest, approval_digest=binding.patch_approval_digest, binding_id=binding.binding_id)) != binding.digest:
                raise ValueError
            SelfDevelopmentApprovedPatchBinder._verify_plan(plan, self.project_key, authority.workspace_path)
            SelfDevelopmentApprovedPatchBinder._verify_approval(approval, plan, self.project_key, authority.workspace_path)
        except Exception as exc:
            if isinstance(exc, (SelfDevelopmentPromotionExecutionError,)):
                raise
            raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion execution chain integrity is invalid.") from exc
        if binding.authority_id != authority.authority_id or binding.authority_digest != authority.digest or binding.candidate_id != authority.candidate_id or binding.candidate_digest != authority.candidate_digest:
            raise SelfDevelopmentPromotionExecutionAuthorizationError("Promotion execution authority and binding do not match.")
        if not binding.promotion_execution_eligible or binding.source_mutation_allowed or binding.main_branch_mutation_allowed:
            raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion execution binding invariants are invalid.")
        if binding.plan_digest != plan.snapshot.digest or binding.preview_digest != approval.preview_digest or binding.patch_approval_digest != approval.digest:
            raise SelfDevelopmentPromotionExecutionAuthorizationError("Promotion execution binding does not authorize the supplied patch.")

    def execute(self, *, authority: SelfDevelopmentPromotionAuthoritySnapshot, binding: SelfDevelopmentApprovedPatchBindingSnapshot, plan: SafePatchPlan, approval: SafePatchApprovalBindingSnapshot, changes: Iterable[PatchChangeRequest]) -> SelfDevelopmentPromotionExecutionSnapshot:
        self._validate_chain(authority=authority, binding=binding, plan=plan, approval=approval)
        payload = tuple(changes)
        payload_digest = _payload_digest(payload)
        try:
            for change in payload:
                plan.assert_change(path=change.path, operation=change.operation, replacement_text=change.replacement_text)
            if len(payload) != plan.snapshot.operation_count or {change.path for change in payload} != {operation.path for operation in plan.snapshot.operations}:
                raise ValueError
        except Exception as exc:
            raise SelfDevelopmentPromotionExecutionAuthorizationError("Promotion change payload is not authorized by the plan.") from exc
        try:
            if self.receipt_store.is_consumed(binding_id=binding.binding_id, binding_digest=binding.digest):
                raise SelfDevelopmentPromotionExecutionReplayError("Promotion binding has already been consumed.")
            if self.claim_store.is_claimed(binding_id=binding.binding_id, binding_digest=binding.digest):
                raise SelfDevelopmentPromotionExecutionRecoveryRequiredError("Promotion execution requires recovery.")
        except SelfDevelopmentPromotionExecutionError:
            raise
        except Exception as exc:
            raise SelfDevelopmentPromotionExecutionIntegrityError("Promotion replay evidence is invalid.") from exc
        claim_payload = {"revision": SELF_DEVELOPMENT_PROMOTION_EXECUTION_CLAIM_REVISION, "workspace_path": authority.workspace_path, "project_key": self.project_key, "authority_id": authority.authority_id, "authority_digest": authority.digest, "binding_id": binding.binding_id, "binding_digest": binding.digest, "candidate_id": authority.candidate_id, "candidate_digest": authority.candidate_digest, "plan_digest": plan.snapshot.digest, "preview_digest": approval.preview_digest, "patch_approval_digest": approval.digest, "change_payload_digest": payload_digest}
        claim_id = "sdpc_" + _digest(claim_payload)[7:31]
        claim = SelfDevelopmentPromotionExecutionClaim(SELF_DEVELOPMENT_PROMOTION_EXECUTION_CLAIM_REVISION, claim_id, authority.workspace_path, self.project_key, authority.authority_id, authority.digest, binding.binding_id, binding.digest, authority.candidate_id, authority.candidate_digest, plan.snapshot.digest, approval.preview_digest, approval.digest, payload_digest, _digest({**claim_payload, "claim_id": claim_id}))
        self.claim_store.claim(claim)
        try:
            execution_receipt = self.safe_patch_executor.execute(plan=plan, changes=payload)
        except Exception as exc:
            raise SelfDevelopmentPromotionExecutionRecoveryRequiredError("Promotion execution requires recovery after executor failure.") from exc
        if not isinstance(execution_receipt, SafePatchExecutionReceipt):
            raise SelfDevelopmentPromotionExecutionIntegrityError("Safe Patch execution receipt is invalid.")
        safe_digest = execution_receipt.digest
        safe_payload = execution_receipt.to_dict()
        safe_payload.pop("digest", None)
        if not isinstance(safe_digest, str) or _SHA256.fullmatch(safe_digest) is None or _digest(safe_payload) != safe_digest:
            raise SelfDevelopmentPromotionExecutionIntegrityError("Safe Patch execution receipt integrity is invalid.")
        safe_id = "spe_" + safe_digest[7:31]
        receipt = SelfDevelopmentPromotionExecutionReceipt(SELF_DEVELOPMENT_PROMOTION_RECEIPT_REVISION, "", authority.workspace_path, self.project_key, binding.binding_id, binding.digest, authority.authority_id, authority.digest, authority.candidate_id, authority.candidate_digest, plan.snapshot.digest, approval.preview_digest, approval.digest, safe_id, safe_digest, True, True, False, "")
        receipt = SelfDevelopmentPromotionExecutionReceipt(**{**receipt.to_dict(), "receipt_id": "sdpr_" + _digest(receipt_payload(receipt, include_id=False))[7:31]})
        receipt = SelfDevelopmentPromotionExecutionReceipt(**{**receipt.to_dict(), "digest": _digest(receipt_payload(receipt))})
        try:
            stored = self.receipt_store.append(receipt)
        except Exception as exc:
            raise SelfDevelopmentPromotionExecutionRecoveryRequiredError("Promotion receipt persistence requires recovery.") from exc
        snapshot_payload = {"revision": SELF_DEVELOPMENT_PROMOTION_EXECUTION_REVISION, "workspace_path": authority.workspace_path, "project_key": self.project_key, "authority_id": authority.authority_id, "authority_digest": authority.digest, "binding_id": binding.binding_id, "binding_digest": binding.digest, "candidate_id": authority.candidate_id, "candidate_digest": authority.candidate_digest, "plan_digest": plan.snapshot.digest, "preview_digest": approval.preview_digest, "patch_approval_digest": approval.digest, "change_payload_digest": payload_digest, "claim_id": claim.claim_id, "claim_digest": claim.digest, "safe_patch_execution_receipt_id": safe_id, "safe_patch_execution_receipt_digest": safe_digest, "promotion_receipt_id": stored.receipt_id, "promotion_receipt_digest": stored.digest, "promotion_executed": True, "source_mutation_performed": True, "main_branch_mutation_performed": False}
        execution_id = "sdpe_" + _digest(snapshot_payload)[7:31]
        full = {**snapshot_payload, "execution_id": execution_id}
        return SelfDevelopmentPromotionExecutionSnapshot(**{**full, "digest": _digest(full)})
