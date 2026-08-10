"""Canonical post-evaluation supervised decision gate."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.improvement.evaluation import (
    SELF_DEVELOPMENT_EVALUATION_REVISION,
    SelfDevelopmentEvaluationObservation,
    SelfDevelopmentEvaluationSnapshot,
    _canonical,
    _payload as evaluation_payload,
)

SELF_DEVELOPMENT_DECISION_GATE_REVISION = "self-development-decision-gate-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_OUTCOMES = frozenset({"pass", "fail", "inconclusive"})


class SelfDevelopmentDecisionGateError(ValueError):
    pass


class SelfDevelopmentDecisionGateValidationError(SelfDevelopmentDecisionGateError):
    pass


class SelfDevelopmentDecisionGateIntegrityError(SelfDevelopmentDecisionGateError):
    pass


class SelfDevelopmentDecisionGateProjectError(SelfDevelopmentDecisionGateError):
    pass


@dataclass(frozen=True)
class SelfDevelopmentDecisionGateSnapshot:
    revision: str
    gate_id: str
    workspace_path: str
    project_key: str
    evaluation_id: str
    evaluation_digest: str
    candidate_id: str
    candidate_digest: str
    proposal_digest: str
    evidence_resolution_digest: str
    evaluation_outcome: str
    gate_status: str
    eligible_for_human_review: bool
    requires_human_approval: bool
    promotion_allowed: bool
    source_mutation_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "gate_id": self.gate_id,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "evaluation_id": self.evaluation_id,
            "evaluation_digest": self.evaluation_digest,
            "candidate_id": self.candidate_id,
            "candidate_digest": self.candidate_digest,
            "proposal_digest": self.proposal_digest,
            "evidence_resolution_digest": self.evidence_resolution_digest,
            "evaluation_outcome": self.evaluation_outcome,
            "gate_status": self.gate_status,
            "eligible_for_human_review": self.eligible_for_human_review,
            "requires_human_approval": self.requires_human_approval,
            "promotion_allowed": self.promotion_allowed,
            "source_mutation_allowed": self.source_mutation_allowed,
            "main_branch_mutation_allowed": self.main_branch_mutation_allowed,
            "digest": self.digest,
        }


def _gate_payload(*, workspace_path: str, project_key: str, evaluation_id: str, evaluation_digest: str, candidate_id: str, candidate_digest: str, proposal_digest: str, evidence_resolution_digest: str, evaluation_outcome: str, gate_status: str, eligible_for_human_review: bool, gate_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision": SELF_DEVELOPMENT_DECISION_GATE_REVISION,
        "workspace_path": workspace_path, "project_key": project_key,
        "evaluation_id": evaluation_id, "evaluation_digest": evaluation_digest,
        "candidate_id": candidate_id, "candidate_digest": candidate_digest,
        "proposal_digest": proposal_digest, "evidence_resolution_digest": evidence_resolution_digest,
        "evaluation_outcome": evaluation_outcome, "gate_status": gate_status,
        "eligible_for_human_review": eligible_for_human_review,
        "requires_human_approval": True, "promotion_allowed": False,
        "source_mutation_allowed": False, "main_branch_mutation_allowed": False,
    }
    if gate_id is not None:
        payload["gate_id"] = gate_id
    return payload


class SelfDevelopmentDecisionGate:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip() or len(project_key) > 160:
            raise SelfDevelopmentDecisionGateProjectError("Decision gate project binding is invalid.")
        self.project_key = project_key

    @staticmethod
    def _verify_evaluation(evaluation: SelfDevelopmentEvaluationSnapshot, project_key: str) -> None:
        if not isinstance(evaluation, SelfDevelopmentEvaluationSnapshot):
            raise SelfDevelopmentDecisionGateValidationError("Decision gate evaluation is invalid.")
        if evaluation.project_key != project_key:
            raise SelfDevelopmentDecisionGateProjectError("Decision gate project binding is invalid.")
        if evaluation.revision != SELF_DEVELOPMENT_EVALUATION_REVISION or not _SHA256.fullmatch(evaluation.digest):
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation integrity is invalid.")
        if any(not _SHA256.fullmatch(value) for value in (evaluation.candidate_digest, evaluation.proposal_digest, evaluation.evidence_resolution_digest)):
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation integrity is invalid.")
        if not evaluation.requires_human_approval or evaluation.promotion_allowed or evaluation.source_mutation_allowed or evaluation.main_branch_mutation_allowed:
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation safety flags are invalid.")
        if evaluation.observation_count != len(evaluation.observations) or not evaluation.observations:
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation observations are invalid.")
        if any(not isinstance(item, SelfDevelopmentEvaluationObservation) for item in evaluation.observations):
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation observations are invalid.")
        ordered = tuple(sorted(evaluation.observations, key=lambda item: (item.check_id, item.outcome, item.evidence_digest)))
        if ordered != evaluation.observations or len({item.check_id for item in ordered}) != len(ordered):
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation observations are invalid.")
        for item in ordered:
            if not isinstance(item, SelfDevelopmentEvaluationObservation) or not item.check_id or item.outcome not in _OUTCOMES or not _SHA256.fullmatch(item.evidence_digest):
                raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation observations are invalid.")
        outcomes = {item.outcome for item in ordered}
        expected = "fail" if "fail" in outcomes else "inconclusive" if "inconclusive" in outcomes else "pass"
        if evaluation.overall_outcome != expected:
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation outcome is inconsistent.")
        base = evaluation_payload(workspace_path=evaluation.workspace_path, project_key=evaluation.project_key, candidate_id=evaluation.candidate_id, candidate_digest=evaluation.candidate_digest, proposal_digest=evaluation.proposal_digest, evidence_resolution_digest=evaluation.evidence_resolution_digest, observations=ordered, observation_count=evaluation.observation_count, overall_outcome=evaluation.overall_outcome)
        if evaluation.evaluation_id != "sde_" + _canonical(base)[7:31]:
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation identity is invalid.")
        payload = evaluation_payload(workspace_path=evaluation.workspace_path, project_key=evaluation.project_key, candidate_id=evaluation.candidate_id, candidate_digest=evaluation.candidate_digest, proposal_digest=evaluation.proposal_digest, evidence_resolution_digest=evaluation.evidence_resolution_digest, observations=ordered, observation_count=evaluation.observation_count, overall_outcome=evaluation.overall_outcome, evaluation_id=evaluation.evaluation_id)
        if _canonical(payload) != evaluation.digest:
            raise SelfDevelopmentDecisionGateIntegrityError("Decision gate evaluation integrity is invalid.")

    def decide(self, *, evaluation: SelfDevelopmentEvaluationSnapshot) -> SelfDevelopmentDecisionGateSnapshot:
        self._verify_evaluation(evaluation, self.project_key)
        gate_status, eligible = {"pass": ("review_required", True), "fail": ("blocked_failed", False), "inconclusive": ("blocked_inconclusive", False)}[evaluation.overall_outcome]
        args = dict(workspace_path=evaluation.workspace_path, project_key=self.project_key, evaluation_id=evaluation.evaluation_id, evaluation_digest=evaluation.digest, candidate_id=evaluation.candidate_id, candidate_digest=evaluation.candidate_digest, proposal_digest=evaluation.proposal_digest, evidence_resolution_digest=evaluation.evidence_resolution_digest, evaluation_outcome=evaluation.overall_outcome, gate_status=gate_status, eligible_for_human_review=eligible)
        gate_id = "sdg_" + _canonical(_gate_payload(**args))[7:31]
        digest = _canonical(_gate_payload(**args, gate_id=gate_id))
        return SelfDevelopmentDecisionGateSnapshot(SELF_DEVELOPMENT_DECISION_GATE_REVISION, gate_id, evaluation.workspace_path, self.project_key, evaluation.evaluation_id, evaluation.digest, evaluation.candidate_id, evaluation.candidate_digest, evaluation.proposal_digest, evaluation.evidence_resolution_digest, evaluation.overall_outcome, gate_status, eligible, True, False, False, False, digest)
