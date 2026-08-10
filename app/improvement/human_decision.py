"""Canonical explicit human decision binding for supervised development."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.improvement.decision_gate import SELF_DEVELOPMENT_DECISION_GATE_REVISION, SelfDevelopmentDecisionGateSnapshot, _canonical, _gate_payload

SELF_DEVELOPMENT_HUMAN_DECISION_REVISION = "self-development-human-decision-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_DECISIONS = frozenset({"approve", "reject"})
_STATUSES = frozenset({"review_required", "blocked_failed", "blocked_inconclusive"})


class SelfDevelopmentHumanDecisionError(ValueError):
    pass


class SelfDevelopmentHumanDecisionValidationError(SelfDevelopmentHumanDecisionError):
    pass


class SelfDevelopmentHumanDecisionIntegrityError(SelfDevelopmentHumanDecisionError):
    pass


class SelfDevelopmentHumanDecisionProjectError(SelfDevelopmentHumanDecisionError):
    pass


class SelfDevelopmentHumanDecisionEligibilityError(SelfDevelopmentHumanDecisionError):
    pass


@dataclass(frozen=True)
class SelfDevelopmentHumanDecisionSnapshot:
    revision: str
    decision_id: str
    workspace_path: str
    project_key: str
    gate_id: str
    gate_digest: str
    evaluation_id: str
    evaluation_digest: str
    candidate_id: str
    candidate_digest: str
    proposal_digest: str
    evidence_resolution_digest: str
    gate_status: str
    human_decision: str
    human_approval_present: bool
    promotion_eligible: bool
    source_mutation_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {"revision": self.revision, "decision_id": self.decision_id, "workspace_path": self.workspace_path, "project_key": self.project_key, "gate_id": self.gate_id, "gate_digest": self.gate_digest, "evaluation_id": self.evaluation_id, "evaluation_digest": self.evaluation_digest, "candidate_id": self.candidate_id, "candidate_digest": self.candidate_digest, "proposal_digest": self.proposal_digest, "evidence_resolution_digest": self.evidence_resolution_digest, "gate_status": self.gate_status, "human_decision": self.human_decision, "human_approval_present": self.human_approval_present, "promotion_eligible": self.promotion_eligible, "source_mutation_allowed": self.source_mutation_allowed, "main_branch_mutation_allowed": self.main_branch_mutation_allowed, "digest": self.digest}


def _gate_without_id(gate: SelfDevelopmentDecisionGateSnapshot) -> dict[str, object]:
    return _gate_payload(workspace_path=gate.workspace_path, project_key=gate.project_key, evaluation_id=gate.evaluation_id, evaluation_digest=gate.evaluation_digest, candidate_id=gate.candidate_id, candidate_digest=gate.candidate_digest, proposal_digest=gate.proposal_digest, evidence_resolution_digest=gate.evidence_resolution_digest, evaluation_outcome=gate.evaluation_outcome, gate_status=gate.gate_status, eligible_for_human_review=gate.eligible_for_human_review)


def _decision_payload(*, gate: SelfDevelopmentDecisionGateSnapshot, decision: str, decision_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"revision": SELF_DEVELOPMENT_HUMAN_DECISION_REVISION, "workspace_path": gate.workspace_path, "project_key": gate.project_key, "gate_id": gate.gate_id, "gate_digest": gate.digest, "evaluation_id": gate.evaluation_id, "evaluation_digest": gate.evaluation_digest, "candidate_id": gate.candidate_id, "candidate_digest": gate.candidate_digest, "proposal_digest": gate.proposal_digest, "evidence_resolution_digest": gate.evidence_resolution_digest, "gate_status": gate.gate_status, "human_decision": decision, "human_approval_present": True, "promotion_eligible": decision == "approve", "source_mutation_allowed": False, "main_branch_mutation_allowed": False}
    if decision_id is not None:
        payload["decision_id"] = decision_id
    return payload


class SelfDevelopmentHumanDecisionBinder:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip() or len(project_key) > 160:
            raise SelfDevelopmentHumanDecisionProjectError("Human decision project binding is invalid.")
        self.project_key = project_key

    @staticmethod
    def _verify_gate(gate: SelfDevelopmentDecisionGateSnapshot, project_key: str) -> None:
        if not isinstance(gate, SelfDevelopmentDecisionGateSnapshot):
            raise SelfDevelopmentHumanDecisionValidationError("Human decision gate is invalid.")
        if gate.project_key != project_key:
            raise SelfDevelopmentHumanDecisionProjectError("Human decision project binding is invalid.")
        if gate.revision != SELF_DEVELOPMENT_DECISION_GATE_REVISION or not _SHA256.fullmatch(gate.digest) or gate.gate_status not in _STATUSES:
            raise SelfDevelopmentHumanDecisionIntegrityError("Human decision gate integrity is invalid.")
        if any(not _SHA256.fullmatch(value) for value in (gate.evaluation_digest, gate.candidate_digest, gate.proposal_digest, gate.evidence_resolution_digest)):
            raise SelfDevelopmentHumanDecisionIntegrityError("Human decision gate integrity is invalid.")
        if not gate.requires_human_approval or gate.promotion_allowed or gate.source_mutation_allowed or gate.main_branch_mutation_allowed:
            raise SelfDevelopmentHumanDecisionIntegrityError("Human decision gate safety flags are invalid.")
        if gate.eligible_for_human_review != (gate.gate_status == "review_required"):
            raise SelfDevelopmentHumanDecisionIntegrityError("Human decision gate eligibility is inconsistent.")
        if gate.gate_id != "sdg_" + _canonical(_gate_without_id(gate))[7:31]:
            raise SelfDevelopmentHumanDecisionIntegrityError("Human decision gate identity is invalid.")
        payload = _gate_payload(workspace_path=gate.workspace_path, project_key=gate.project_key, evaluation_id=gate.evaluation_id, evaluation_digest=gate.evaluation_digest, candidate_id=gate.candidate_id, candidate_digest=gate.candidate_digest, proposal_digest=gate.proposal_digest, evidence_resolution_digest=gate.evidence_resolution_digest, evaluation_outcome=gate.evaluation_outcome, gate_status=gate.gate_status, eligible_for_human_review=gate.eligible_for_human_review, gate_id=gate.gate_id)
        if _canonical(payload) != gate.digest:
            raise SelfDevelopmentHumanDecisionIntegrityError("Human decision gate integrity is invalid.")

    def bind(self, *, gate: SelfDevelopmentDecisionGateSnapshot, decision: str) -> SelfDevelopmentHumanDecisionSnapshot:
        self._verify_gate(gate, self.project_key)
        if not isinstance(decision, str) or decision not in _DECISIONS:
            raise SelfDevelopmentHumanDecisionValidationError("Human decision must be approve or reject.")
        if gate.gate_status != "review_required" or not gate.eligible_for_human_review:
            raise SelfDevelopmentHumanDecisionEligibilityError("This gate is not eligible for human decision binding.")
        decision_id = "sdh_" + _canonical(_decision_payload(gate=gate, decision=decision))[7:31]
        digest = _canonical(_decision_payload(gate=gate, decision=decision, decision_id=decision_id))
        return SelfDevelopmentHumanDecisionSnapshot(SELF_DEVELOPMENT_HUMAN_DECISION_REVISION, decision_id, gate.workspace_path, self.project_key, gate.gate_id, gate.digest, gate.evaluation_id, gate.evaluation_digest, gate.candidate_id, gate.candidate_digest, gate.proposal_digest, gate.evidence_resolution_digest, gate.gate_status, decision, True, decision == "approve", False, False, digest)
