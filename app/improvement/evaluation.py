"""Canonical isolated candidate evaluation artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.improvement.candidate import (
    SELF_DEVELOPMENT_CANDIDATE_REVISION,
    SelfDevelopmentCandidateSnapshot,
    _candidate_payload,
)
from app.improvement.evidence import _canonical

SELF_DEVELOPMENT_EVALUATION_REVISION = "self-development-evaluation-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_OUTCOMES = frozenset({"pass", "fail", "inconclusive"})


class SelfDevelopmentEvaluationError(ValueError):
    pass


class SelfDevelopmentEvaluationValidationError(SelfDevelopmentEvaluationError):
    pass


class SelfDevelopmentEvaluationIntegrityError(SelfDevelopmentEvaluationError):
    pass


class SelfDevelopmentEvaluationProjectError(SelfDevelopmentEvaluationError):
    pass


@dataclass(frozen=True)
class SelfDevelopmentEvaluationObservation:
    check_id: str
    outcome: str
    evidence_digest: str
    category: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "check_id": self.check_id,
            "outcome": self.outcome,
            "evidence_digest": self.evidence_digest,
        }
        if self.category:
            payload["category"] = self.category
        return payload


@dataclass(frozen=True)
class SelfDevelopmentEvaluationSnapshot:
    revision: str
    evaluation_id: str
    workspace_path: str
    project_key: str
    candidate_id: str
    candidate_digest: str
    proposal_digest: str
    evidence_resolution_digest: str
    observations: tuple[SelfDevelopmentEvaluationObservation, ...]
    observation_count: int
    overall_outcome: str
    requires_human_approval: bool
    promotion_allowed: bool
    source_mutation_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "evaluation_id": self.evaluation_id,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "candidate_id": self.candidate_id,
            "candidate_digest": self.candidate_digest,
            "proposal_digest": self.proposal_digest,
            "evidence_resolution_digest": self.evidence_resolution_digest,
            "observations": [item.to_dict() for item in self.observations],
            "observation_count": self.observation_count,
            "overall_outcome": self.overall_outcome,
            "requires_human_approval": self.requires_human_approval,
            "promotion_allowed": self.promotion_allowed,
            "source_mutation_allowed": self.source_mutation_allowed,
            "main_branch_mutation_allowed": self.main_branch_mutation_allowed,
            "digest": self.digest,
        }


def _payload(
    *,
    workspace_path: str,
    project_key: str,
    candidate_id: str,
    candidate_digest: str,
    proposal_digest: str,
    evidence_resolution_digest: str,
    observations: tuple[SelfDevelopmentEvaluationObservation, ...],
    observation_count: int,
    overall_outcome: str,
    evaluation_id: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "revision": SELF_DEVELOPMENT_EVALUATION_REVISION,
        "workspace_path": workspace_path,
        "project_key": project_key,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "proposal_digest": proposal_digest,
        "evidence_resolution_digest": evidence_resolution_digest,
        "observations": [item.to_dict() for item in observations],
        "observation_count": observation_count,
        "overall_outcome": overall_outcome,
        "requires_human_approval": True,
        "promotion_allowed": False,
        "source_mutation_allowed": False,
        "main_branch_mutation_allowed": False,
    }
    if evaluation_id is not None:
        result["evaluation_id"] = evaluation_id
    return result


class SelfDevelopmentCandidateEvaluator:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip() or len(project_key) > 160:
            raise SelfDevelopmentEvaluationProjectError("Evaluation project binding is invalid.")
        self.project_key = project_key

    @staticmethod
    def _verify_candidate(candidate: SelfDevelopmentCandidateSnapshot, project_key: str) -> None:
        if not isinstance(candidate, SelfDevelopmentCandidateSnapshot):
            raise SelfDevelopmentEvaluationValidationError("Evaluation candidate is invalid.")
        if candidate.project_key != project_key:
            raise SelfDevelopmentEvaluationProjectError("Evaluation project binding is invalid.")
        if candidate.revision != SELF_DEVELOPMENT_CANDIDATE_REVISION or not _SHA256.fullmatch(candidate.digest):
            raise SelfDevelopmentEvaluationIntegrityError("Evaluation candidate integrity is invalid.")
        if not _SHA256.fullmatch(candidate.proposal_digest) or not _SHA256.fullmatch(candidate.evidence_resolution_digest):
            raise SelfDevelopmentEvaluationIntegrityError("Evaluation candidate integrity is invalid.")
        if any(not _SHA256.fullmatch(item) for item in candidate.evidence_item_digests):
            raise SelfDevelopmentEvaluationIntegrityError("Evaluation candidate integrity is invalid.")
        if not candidate.requires_human_approval or candidate.execution_allowed or candidate.source_mutation_allowed or candidate.main_branch_mutation_allowed:
            raise SelfDevelopmentEvaluationIntegrityError("Evaluation candidate safety flags are invalid.")
        base = _candidate_payload(
            workspace_path=candidate.workspace_path,
            project_key=candidate.project_key,
            proposal_digest=candidate.proposal_digest,
            evidence_resolution_digest=candidate.evidence_resolution_digest,
            evidence_item_digests=candidate.evidence_item_digests,
            candidate_kind=candidate.candidate_kind,
        )
        expected_id = "sdc_" + _canonical(base)[7:31]
        if candidate.candidate_id != expected_id:
            raise SelfDevelopmentEvaluationIntegrityError("Evaluation candidate identity is invalid.")
        payload = _candidate_payload(
            workspace_path=candidate.workspace_path,
            project_key=candidate.project_key,
            proposal_digest=candidate.proposal_digest,
            evidence_resolution_digest=candidate.evidence_resolution_digest,
            evidence_item_digests=candidate.evidence_item_digests,
            candidate_kind=candidate.candidate_kind,
            candidate_id=candidate.candidate_id,
        )
        if _canonical(payload) != candidate.digest:
            raise SelfDevelopmentEvaluationIntegrityError("Evaluation candidate integrity is invalid.")

    @staticmethod
    def _observations(values: tuple[SelfDevelopmentEvaluationObservation, ...]) -> tuple[SelfDevelopmentEvaluationObservation, ...]:
        try:
            items = tuple(values)
        except TypeError:
            raise SelfDevelopmentEvaluationValidationError("Evaluation observations are invalid.") from None
        if not items:
            raise SelfDevelopmentEvaluationValidationError("At least one evaluation observation is required.")
        for item in items:
            if not isinstance(item, SelfDevelopmentEvaluationObservation):
                raise SelfDevelopmentEvaluationValidationError("Evaluation observation is invalid.")
            if not isinstance(item.check_id, str) or not item.check_id.strip() or len(item.check_id) > 128 or "\x00" in item.check_id:
                raise SelfDevelopmentEvaluationValidationError("Evaluation check identifier is invalid.")
            if item.outcome not in _OUTCOMES:
                raise SelfDevelopmentEvaluationValidationError("Evaluation outcome is invalid.")
            if not isinstance(item.evidence_digest, str) or not _SHA256.fullmatch(item.evidence_digest):
                raise SelfDevelopmentEvaluationValidationError("Evaluation evidence digest is invalid.")
            if not isinstance(item.category, str) or len(item.category) > 64 or "\x00" in item.category:
                raise SelfDevelopmentEvaluationValidationError("Evaluation category is invalid.")
        ordered = tuple(sorted(items, key=lambda item: (item.check_id, item.outcome, item.evidence_digest)))
        check_ids = [item.check_id for item in ordered]
        if len(check_ids) != len(set(check_ids)):
            raise SelfDevelopmentEvaluationValidationError("Evaluation check identifiers must be unique.")
        return ordered

    def evaluate(
        self,
        *,
        candidate: SelfDevelopmentCandidateSnapshot,
        observations: tuple[SelfDevelopmentEvaluationObservation, ...],
    ) -> SelfDevelopmentEvaluationSnapshot:
        self._verify_candidate(candidate, self.project_key)
        ordered = self._observations(observations)
        outcomes = {item.outcome for item in ordered}
        overall = "fail" if "fail" in outcomes else "inconclusive" if "inconclusive" in outcomes else "pass"
        preimage = _payload(
            workspace_path=candidate.workspace_path,
            project_key=self.project_key,
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.digest,
            proposal_digest=candidate.proposal_digest,
            evidence_resolution_digest=candidate.evidence_resolution_digest,
            observations=ordered,
            observation_count=len(ordered),
            overall_outcome=overall,
        )
        evaluation_id = "sde_" + _canonical(preimage)[7:31]
        payload = _payload(
            workspace_path=candidate.workspace_path,
            project_key=self.project_key,
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.digest,
            proposal_digest=candidate.proposal_digest,
            evidence_resolution_digest=candidate.evidence_resolution_digest,
            observations=ordered,
            observation_count=len(ordered),
            overall_outcome=overall,
            evaluation_id=evaluation_id,
        )
        digest = _canonical(payload)
        return SelfDevelopmentEvaluationSnapshot(
            SELF_DEVELOPMENT_EVALUATION_REVISION,
            evaluation_id,
            candidate.workspace_path,
            self.project_key,
            candidate.candidate_id,
            candidate.digest,
            candidate.proposal_digest,
            candidate.evidence_resolution_digest,
            ordered,
            len(ordered),
            overall,
            True,
            False,
            False,
            False,
            digest,
        )
