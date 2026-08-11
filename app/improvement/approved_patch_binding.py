"""Canonical binding between an approved self-development chain and Safe Patch."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.improvement.promotion_authority import (
    SELF_DEVELOPMENT_PROMOTION_AUTHORITY_REVISION,
    SelfDevelopmentPromotionAuthoritySnapshot,
    _authority_payload,
)
from app.improvement.human_decision import _canonical
from app.workspace.patch_approval import (
    SAFE_PATCH_APPROVAL_BINDING_REVISION,
    SafePatchApprovalBindingSnapshot,
    SafePatchApprovalBuilder,
)
from app.workspace.patch_plan import SAFE_PATCH_PLAN_REVISION, SafePatchPlan

SELF_DEVELOPMENT_APPROVED_PATCH_BINDING_REVISION = "self-development-approved-patch-binding-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class SelfDevelopmentApprovedPatchBindingError(ValueError):
    pass


class SelfDevelopmentApprovedPatchBindingValidationError(SelfDevelopmentApprovedPatchBindingError):
    pass


class SelfDevelopmentApprovedPatchBindingIntegrityError(SelfDevelopmentApprovedPatchBindingError):
    pass


class SelfDevelopmentApprovedPatchBindingProjectError(SelfDevelopmentApprovedPatchBindingError):
    pass


class SelfDevelopmentApprovedPatchBindingAuthorizationError(SelfDevelopmentApprovedPatchBindingError):
    pass


@dataclass(frozen=True)
class SelfDevelopmentApprovedPatchBindingSnapshot:
    revision: str
    binding_id: str
    workspace_path: str
    project_key: str
    authority_id: str
    authority_digest: str
    decision_id: str
    decision_digest: str
    candidate_id: str
    candidate_digest: str
    plan_digest: str
    preview_digest: str
    patch_approval_digest: str
    binding_scope: str
    promotion_execution_eligible: bool
    source_mutation_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision, "binding_id": self.binding_id,
            "workspace_path": self.workspace_path, "project_key": self.project_key,
            "authority_id": self.authority_id, "authority_digest": self.authority_digest,
            "decision_id": self.decision_id, "decision_digest": self.decision_digest,
            "candidate_id": self.candidate_id, "candidate_digest": self.candidate_digest,
            "plan_digest": self.plan_digest, "preview_digest": self.preview_digest,
            "patch_approval_digest": self.patch_approval_digest,
            "binding_scope": self.binding_scope,
            "promotion_execution_eligible": self.promotion_execution_eligible,
            "source_mutation_allowed": self.source_mutation_allowed,
            "main_branch_mutation_allowed": self.main_branch_mutation_allowed,
            "digest": self.digest,
        }


def _binding_payload(*, authority: SelfDevelopmentPromotionAuthoritySnapshot, plan_digest: str, preview_digest: str, approval_digest: str, binding_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision": SELF_DEVELOPMENT_APPROVED_PATCH_BINDING_REVISION,
        "workspace_path": authority.workspace_path, "project_key": authority.project_key,
        "authority_id": authority.authority_id, "authority_digest": authority.digest,
        "decision_id": authority.decision_id, "decision_digest": authority.decision_digest,
        "candidate_id": authority.candidate_id, "candidate_digest": authority.candidate_digest,
        "plan_digest": plan_digest, "preview_digest": preview_digest,
        "patch_approval_digest": approval_digest,
        "binding_scope": "self-development-approved-patch",
        "promotion_execution_eligible": True,
        "source_mutation_allowed": False, "main_branch_mutation_allowed": False,
    }
    if binding_id is not None:
        payload["binding_id"] = binding_id
    return payload


@dataclass(frozen=True)
class _DecisionProjection:
    workspace_path: str
    project_key: str
    decision_id: str
    digest: str
    gate_id: str
    gate_digest: str
    evaluation_id: str
    evaluation_digest: str
    candidate_id: str
    candidate_digest: str
    proposal_digest: str
    evidence_resolution_digest: str
    human_decision: str


def _decision_projection(authority: SelfDevelopmentPromotionAuthoritySnapshot) -> _DecisionProjection:
    return _DecisionProjection(authority.workspace_path, authority.project_key, authority.decision_id, authority.decision_digest, authority.gate_id, authority.gate_digest, authority.evaluation_id, authority.evaluation_digest, authority.candidate_id, authority.candidate_digest, authority.proposal_digest, authority.evidence_resolution_digest, authority.human_decision)


class SelfDevelopmentApprovedPatchBinder:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip() or len(project_key) > 160:
            raise SelfDevelopmentApprovedPatchBindingProjectError("Approved patch binding project is invalid.")
        self.project_key = project_key

    @staticmethod
    def _verify_authority(authority: SelfDevelopmentPromotionAuthoritySnapshot, project_key: str) -> None:
        if not isinstance(authority, SelfDevelopmentPromotionAuthoritySnapshot):
            raise SelfDevelopmentApprovedPatchBindingValidationError("Promotion authority is invalid.")
        if authority.project_key != project_key:
            raise SelfDevelopmentApprovedPatchBindingProjectError("Approved patch binding project mismatch.")
        if authority.revision != SELF_DEVELOPMENT_PROMOTION_AUTHORITY_REVISION or not _SHA256.fullmatch(authority.digest):
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Promotion authority integrity is invalid.")
        if any(not _SHA256.fullmatch(value) for value in (authority.decision_digest, authority.gate_digest, authority.evaluation_digest, authority.candidate_digest, authority.proposal_digest, authority.evidence_resolution_digest)):
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Promotion authority integrity is invalid.")
        projected = _decision_projection(authority)
        expected_id = "sda_" + _canonical(_authority_payload(decision=projected))[7:31]
        if authority.authority_id != expected_id:
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Promotion authority identity is invalid.")
        if _canonical(_authority_payload(decision=projected, authority_id=authority.authority_id)) != authority.digest:
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Promotion authority integrity is invalid.")
        if authority.human_decision != "approve" or authority.authority_scope != "self-development-promotion" or not authority.promotion_authorized or authority.source_mutation_allowed or authority.main_branch_mutation_allowed:
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Promotion authority canonical invariants are invalid.")

    @staticmethod
    def _verify_plan(plan: SafePatchPlan, project_key: str, workspace_path: str) -> None:
        if not isinstance(plan, SafePatchPlan):
            raise SelfDevelopmentApprovedPatchBindingValidationError("Safe Patch plan is invalid.")
        snapshot = plan.snapshot
        if (snapshot.project_key, snapshot.workspace_path) != (project_key, workspace_path) or snapshot.revision != SAFE_PATCH_PLAN_REVISION:
            raise SelfDevelopmentApprovedPatchBindingProjectError("Safe Patch plan project/workspace mismatch.")
        try:
            validator = SafePatchApprovalBuilder(project_root=plan._project_root, workspace_path=workspace_path, project_key=project_key)
            validator._validate_plan(plan)
        except Exception as exc:
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Safe Patch plan integrity is invalid.") from exc

    @staticmethod
    def _verify_approval(approval: SafePatchApprovalBindingSnapshot, plan: SafePatchPlan, project_key: str, workspace_path: str) -> None:
        if not isinstance(approval, SafePatchApprovalBindingSnapshot):
            raise SelfDevelopmentApprovedPatchBindingValidationError("Safe Patch approval is invalid.")
        try:
            SafePatchApprovalBuilder._verify_supplied_binding(approval)
        except Exception as exc:
            raise SelfDevelopmentApprovedPatchBindingIntegrityError("Safe Patch approval integrity is invalid.") from exc
        snapshot = plan.snapshot
        if (approval.project_key, approval.workspace_path) != (project_key, workspace_path):
            raise SelfDevelopmentApprovedPatchBindingProjectError("Safe Patch approval project/workspace mismatch.")
        if approval.plan_digest != snapshot.digest or approval.operations != snapshot.operations or approval.operation_count != snapshot.operation_count:
            raise SelfDevelopmentApprovedPatchBindingAuthorizationError("Safe Patch approval does not belong to the supplied plan.")

    def bind(self, *, authority: SelfDevelopmentPromotionAuthoritySnapshot, plan: SafePatchPlan, approval: SafePatchApprovalBindingSnapshot) -> SelfDevelopmentApprovedPatchBindingSnapshot:
        self._verify_authority(authority, self.project_key)
        workspace = authority.workspace_path
        self._verify_plan(plan, self.project_key, workspace)
        self._verify_approval(approval, plan, self.project_key, workspace)
        preimage = _binding_payload(authority=authority, plan_digest=plan.snapshot.digest, preview_digest=approval.preview_digest, approval_digest=approval.digest)
        binding_id = "sdpb_" + _canonical(preimage)[7:31]
        digest = _canonical(_binding_payload(authority=authority, plan_digest=plan.snapshot.digest, preview_digest=approval.preview_digest, approval_digest=approval.digest, binding_id=binding_id))
        return SelfDevelopmentApprovedPatchBindingSnapshot(SELF_DEVELOPMENT_APPROVED_PATCH_BINDING_REVISION, binding_id, workspace, self.project_key, authority.authority_id, authority.digest, authority.decision_id, authority.decision_digest, authority.candidate_id, authority.candidate_digest, plan.snapshot.digest, approval.preview_digest, approval.digest, "self-development-approved-patch", True, False, False, digest)
