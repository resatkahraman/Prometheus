"""Canonical supervised promotion authority issuance."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.improvement.human_decision import (
    SELF_DEVELOPMENT_HUMAN_DECISION_REVISION,
    SelfDevelopmentHumanDecisionSnapshot,
    _canonical,
    _decision_payload,
)

SELF_DEVELOPMENT_PROMOTION_AUTHORITY_REVISION = "self-development-promotion-authority-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class SelfDevelopmentPromotionAuthorityError(ValueError):
    pass


class SelfDevelopmentPromotionAuthorityValidationError(SelfDevelopmentPromotionAuthorityError):
    pass


class SelfDevelopmentPromotionAuthorityIntegrityError(SelfDevelopmentPromotionAuthorityError):
    pass


class SelfDevelopmentPromotionAuthorityProjectError(SelfDevelopmentPromotionAuthorityError):
    pass


class SelfDevelopmentPromotionAuthorityEligibilityError(SelfDevelopmentPromotionAuthorityError):
    pass


@dataclass(frozen=True)
class SelfDevelopmentPromotionAuthoritySnapshot:
    revision: str
    authority_id: str
    workspace_path: str
    project_key: str
    decision_id: str
    decision_digest: str
    gate_id: str
    gate_digest: str
    evaluation_id: str
    evaluation_digest: str
    candidate_id: str
    candidate_digest: str
    proposal_digest: str
    evidence_resolution_digest: str
    human_decision: str
    authority_scope: str
    promotion_authorized: bool
    source_mutation_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision, "authority_id": self.authority_id,
            "workspace_path": self.workspace_path, "project_key": self.project_key,
            "decision_id": self.decision_id, "decision_digest": self.decision_digest,
            "gate_id": self.gate_id, "gate_digest": self.gate_digest,
            "evaluation_id": self.evaluation_id, "evaluation_digest": self.evaluation_digest,
            "candidate_id": self.candidate_id, "candidate_digest": self.candidate_digest,
            "proposal_digest": self.proposal_digest, "evidence_resolution_digest": self.evidence_resolution_digest,
            "human_decision": self.human_decision, "authority_scope": self.authority_scope,
            "promotion_authorized": self.promotion_authorized,
            "source_mutation_allowed": self.source_mutation_allowed,
            "main_branch_mutation_allowed": self.main_branch_mutation_allowed,
            "digest": self.digest,
        }


def _authority_payload(*, decision: SelfDevelopmentHumanDecisionSnapshot, authority_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision": SELF_DEVELOPMENT_PROMOTION_AUTHORITY_REVISION,
        "workspace_path": decision.workspace_path, "project_key": decision.project_key,
        "decision_id": decision.decision_id, "decision_digest": decision.digest,
        "gate_id": decision.gate_id, "gate_digest": decision.gate_digest,
        "evaluation_id": decision.evaluation_id, "evaluation_digest": decision.evaluation_digest,
        "candidate_id": decision.candidate_id, "candidate_digest": decision.candidate_digest,
        "proposal_digest": decision.proposal_digest, "evidence_resolution_digest": decision.evidence_resolution_digest,
        "human_decision": decision.human_decision, "authority_scope": "self-development-promotion",
        "promotion_authorized": True, "source_mutation_allowed": False, "main_branch_mutation_allowed": False,
    }
    if authority_id is not None:
        payload["authority_id"] = authority_id
    return payload


class SelfDevelopmentPromotionAuthorityIssuer:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip() or len(project_key) > 160:
            raise SelfDevelopmentPromotionAuthorityProjectError("Promotion authority project binding is invalid.")
        self.project_key = project_key

    @staticmethod
    def _verify_decision(decision: SelfDevelopmentHumanDecisionSnapshot, project_key: str) -> None:
        if not isinstance(decision, SelfDevelopmentHumanDecisionSnapshot):
            raise SelfDevelopmentPromotionAuthorityValidationError("Promotion authority decision is invalid.")
        if decision.project_key != project_key:
            raise SelfDevelopmentPromotionAuthorityProjectError("Promotion authority project binding is invalid.")
        if decision.revision != SELF_DEVELOPMENT_HUMAN_DECISION_REVISION or not _SHA256.fullmatch(decision.digest):
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority decision integrity is invalid.")
        if any(not _SHA256.fullmatch(value) for value in (decision.gate_digest, decision.evaluation_digest, decision.candidate_digest, decision.proposal_digest, decision.evidence_resolution_digest)):
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority decision integrity is invalid.")
        if decision.human_decision not in {"approve", "reject"} or not decision.human_approval_present or decision.source_mutation_allowed or decision.main_branch_mutation_allowed:
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority decision semantics are invalid.")
        if decision.promotion_eligible != (decision.human_decision == "approve"):
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority decision eligibility is inconsistent.")
        expected_id = "sdh_" + _canonical(_decision_payload(gate=type("Gate", (), {"workspace_path": decision.workspace_path, "project_key": decision.project_key, "gate_id": decision.gate_id, "digest": decision.gate_digest, "evaluation_id": decision.evaluation_id, "evaluation_digest": decision.evaluation_digest, "candidate_id": decision.candidate_id, "candidate_digest": decision.candidate_digest, "proposal_digest": decision.proposal_digest, "evidence_resolution_digest": decision.evidence_resolution_digest, "gate_status": decision.gate_status}), decision=decision.human_decision))[7:31]
        if decision.decision_id != expected_id:
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority decision identity is invalid.")
        payload = _decision_payload(gate=type("Gate", (), {"workspace_path": decision.workspace_path, "project_key": decision.project_key, "gate_id": decision.gate_id, "digest": decision.gate_digest, "evaluation_id": decision.evaluation_id, "evaluation_digest": decision.evaluation_digest, "candidate_id": decision.candidate_id, "candidate_digest": decision.candidate_digest, "proposal_digest": decision.proposal_digest, "evidence_resolution_digest": decision.evidence_resolution_digest, "gate_status": decision.gate_status}), decision=decision.human_decision, decision_id=decision.decision_id)
        if _canonical(payload) != decision.digest:
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority decision integrity is invalid.")
        if decision.human_decision == "approve" and decision.gate_status != "review_required":
            raise SelfDevelopmentPromotionAuthorityIntegrityError("Promotion authority gate status is invalid.")

    def issue(self, *, decision: SelfDevelopmentHumanDecisionSnapshot) -> SelfDevelopmentPromotionAuthoritySnapshot:
        self._verify_decision(decision, self.project_key)
        if decision.human_decision != "approve":
            raise SelfDevelopmentPromotionAuthorityEligibilityError("Only an explicit approve decision is eligible for promotion authority.")
        preimage = _authority_payload(decision=decision)
        authority_id = "sda_" + _canonical(preimage)[7:31]
        digest = _canonical(_authority_payload(decision=decision, authority_id=authority_id))
        return SelfDevelopmentPromotionAuthoritySnapshot(
            SELF_DEVELOPMENT_PROMOTION_AUTHORITY_REVISION, authority_id, decision.workspace_path, self.project_key,
            decision.decision_id, decision.digest, decision.gate_id, decision.gate_digest, decision.evaluation_id,
            decision.evaluation_digest, decision.candidate_id, decision.candidate_digest, decision.proposal_digest,
            decision.evidence_resolution_digest, decision.human_decision, "self-development-promotion", True, False, False, digest,
        )
