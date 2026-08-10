"""Canonical, deterministic self-development candidate materialization."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from app.improvement.evidence import (
    SELF_DEVELOPMENT_EVIDENCE_REVISION,
    ResolvedSelfDevelopmentEvidence,
    SelfDevelopmentEvidenceResolution,
    _canonical,
)
from app.improvement.proposal import (
    SELF_DEVELOPMENT_PROPOSAL_REVISION,
    SelfDevelopmentProposalSnapshot,
    _SHA256,
    _digest,
)

SELF_DEVELOPMENT_CANDIDATE_REVISION = "self-development-candidate-v1"


class SelfDevelopmentCandidateError(ValueError):
    pass


class SelfDevelopmentCandidateValidationError(SelfDevelopmentCandidateError):
    pass


class SelfDevelopmentCandidateIntegrityError(SelfDevelopmentCandidateError):
    pass


class SelfDevelopmentCandidateProjectError(SelfDevelopmentCandidateError):
    pass


@dataclass(frozen=True)
class SelfDevelopmentCandidateSnapshot:
    revision: str
    candidate_id: str
    workspace_path: str
    project_key: str
    proposal_digest: str
    evidence_resolution_digest: str
    evidence_item_digests: tuple[str, ...]
    candidate_kind: str
    requires_human_approval: bool
    execution_allowed: bool
    source_mutation_allowed: bool
    main_branch_mutation_allowed: bool
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "candidate_id": self.candidate_id,
            "workspace_path": self.workspace_path,
            "project_key": self.project_key,
            "proposal_digest": self.proposal_digest,
            "evidence_resolution_digest": self.evidence_resolution_digest,
            "evidence_item_digests": list(self.evidence_item_digests),
            "candidate_kind": self.candidate_kind,
            "requires_human_approval": self.requires_human_approval,
            "execution_allowed": self.execution_allowed,
            "source_mutation_allowed": self.source_mutation_allowed,
            "main_branch_mutation_allowed": self.main_branch_mutation_allowed,
            "digest": self.digest,
        }


def _candidate_payload(
    *,
    workspace_path: str,
    project_key: str,
    proposal_digest: str,
    evidence_resolution_digest: str,
    evidence_item_digests: tuple[str, ...],
    candidate_kind: str,
    candidate_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision": SELF_DEVELOPMENT_CANDIDATE_REVISION,
        "workspace_path": workspace_path,
        "project_key": project_key,
        "proposal_digest": proposal_digest,
        "evidence_resolution_digest": evidence_resolution_digest,
        "evidence_item_digests": list(evidence_item_digests),
        "candidate_kind": candidate_kind,
        "requires_human_approval": True,
        "execution_allowed": False,
        "source_mutation_allowed": False,
        "main_branch_mutation_allowed": False,
    }
    if candidate_id is not None:
        payload["candidate_id"] = candidate_id
    return payload


class SelfDevelopmentCandidateMaterializer:
    def __init__(self, *, project_key: str) -> None:
        if not isinstance(project_key, str) or not project_key.strip() or len(project_key) > 160:
            raise SelfDevelopmentCandidateProjectError("Candidate project binding is invalid.")
        self.project_key = project_key

    @staticmethod
    def _verify_proposal(proposal: SelfDevelopmentProposalSnapshot, project_key: str) -> None:
        if not isinstance(proposal, SelfDevelopmentProposalSnapshot):
            raise SelfDevelopmentCandidateValidationError("Candidate proposal is invalid.")
        if proposal.project_key != project_key:
            raise SelfDevelopmentCandidateProjectError("Candidate project binding is invalid.")
        if proposal.revision != SELF_DEVELOPMENT_PROPOSAL_REVISION or not _SHA256.fullmatch(proposal.digest):
            raise SelfDevelopmentCandidateIntegrityError("Candidate proposal integrity is invalid.")
        payload = proposal.to_dict()
        digest = payload.pop("digest", None)
        if digest != proposal.digest or _digest(payload) != proposal.digest:
            raise SelfDevelopmentCandidateIntegrityError("Candidate proposal integrity is invalid.")

    @staticmethod
    def _verify_evidence(
        evidence: SelfDevelopmentEvidenceResolution,
        proposal: SelfDevelopmentProposalSnapshot,
        project_key: str,
    ) -> tuple[str, ...]:
        if not isinstance(evidence, SelfDevelopmentEvidenceResolution):
            raise SelfDevelopmentCandidateValidationError("Candidate evidence resolution is invalid.")
        if evidence.project_key != project_key:
            raise SelfDevelopmentCandidateProjectError("Candidate project binding is invalid.")
        if evidence.proposal_digest != proposal.digest:
            raise SelfDevelopmentCandidateIntegrityError("Candidate proposal and evidence do not match.")
        if evidence.revision != SELF_DEVELOPMENT_EVIDENCE_REVISION or not _SHA256.fullmatch(evidence.digest):
            raise SelfDevelopmentCandidateIntegrityError("Candidate evidence integrity is invalid.")
        if evidence.evidence_count != len(evidence.evidence):
            raise SelfDevelopmentCandidateIntegrityError("Candidate evidence integrity is invalid.")

        item_digests: list[str] = []
        previous_key: tuple[str, str, str] | None = None
        for item in evidence.evidence:
            if not isinstance(item, ResolvedSelfDevelopmentEvidence):
                raise SelfDevelopmentCandidateIntegrityError("Candidate evidence item is invalid.")
            if item.revision != SELF_DEVELOPMENT_EVIDENCE_REVISION or item.project_key != project_key:
                raise SelfDevelopmentCandidateIntegrityError("Candidate evidence item is invalid.")
            if not _SHA256.fullmatch(item.digest):
                raise SelfDevelopmentCandidateIntegrityError("Candidate evidence item is invalid.")
            payload = item.to_dict()
            digest = payload.pop("digest", None)
            if digest != item.digest or _canonical(payload) != item.digest:
                raise SelfDevelopmentCandidateIntegrityError("Candidate evidence item integrity is invalid.")
            key = (item.kind, item.reference_id, item.digest)
            if previous_key is not None and key < previous_key:
                raise SelfDevelopmentCandidateIntegrityError("Candidate evidence ordering is invalid.")
            previous_key = key
            item_digests.append(item.digest)

        aggregate = {
            "revision": SELF_DEVELOPMENT_EVIDENCE_REVISION,
            "project_key": project_key,
            "proposal_digest": proposal.digest,
            "evidence": [item.to_dict() for item in evidence.evidence],
            "evidence_count": evidence.evidence_count,
        }
        if _canonical(aggregate) != evidence.digest:
            raise SelfDevelopmentCandidateIntegrityError("Candidate evidence integrity is invalid.")
        return tuple(item_digests)

    def materialize(
        self,
        *,
        proposal: SelfDevelopmentProposalSnapshot,
        evidence: SelfDevelopmentEvidenceResolution,
    ) -> SelfDevelopmentCandidateSnapshot:
        self._verify_proposal(proposal, self.project_key)
        item_digests = self._verify_evidence(evidence, proposal, self.project_key)
        preimage = _candidate_payload(
            workspace_path=proposal.workspace_path,
            project_key=self.project_key,
            proposal_digest=proposal.digest,
            evidence_resolution_digest=evidence.digest,
            evidence_item_digests=item_digests,
            candidate_kind=proposal.kind,
        )
        raw = json.dumps(preimage, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        candidate_id = "sdc_" + hashlib.sha256(raw).hexdigest()[:24]
        payload = _candidate_payload(
            workspace_path=proposal.workspace_path,
            project_key=self.project_key,
            proposal_digest=proposal.digest,
            evidence_resolution_digest=evidence.digest,
            evidence_item_digests=item_digests,
            candidate_kind=proposal.kind,
            candidate_id=candidate_id,
        )
        digest = _canonical(payload)
        return SelfDevelopmentCandidateSnapshot(
            SELF_DEVELOPMENT_CANDIDATE_REVISION,
            candidate_id,
            proposal.workspace_path,
            self.project_key,
            proposal.digest,
            evidence.digest,
            item_digests,
            proposal.kind,
            True,
            False,
            False,
            False,
            digest,
        )
