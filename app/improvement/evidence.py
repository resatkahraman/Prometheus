"""Read-only trusted evidence resolution for supervised self-development."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any

from app.improvement.proposal import (
    SelfDevelopmentEvidenceReference,
    SelfDevelopmentProposalSnapshot,
    _EVIDENCE_KINDS,
)
from app.improvement.store import ImprovementStore
from app.supervisor.execution_receipts import ExecutionReceiptIntegrityError, ExecutionReceiptStore

SELF_DEVELOPMENT_EVIDENCE_REVISION = "self-development-evidence-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_HOST_PATH = re.compile(r"(?:^[A-Za-z]:[\\/])|(?:^/(?:home|Users|tmp)(?:/|$))")
_MAX_FACTS = 32
_MAX_STRING = 512


class SelfDevelopmentEvidenceResolutionError(ValueError):
    pass


class SelfDevelopmentEvidenceNotFoundError(SelfDevelopmentEvidenceResolutionError):
    pass


class SelfDevelopmentEvidenceIntegrityError(SelfDevelopmentEvidenceResolutionError):
    pass


class SelfDevelopmentEvidenceProjectError(SelfDevelopmentEvidenceResolutionError):
    pass


def _canonical(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _safe_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        result = value
    elif isinstance(value, float) and math.isfinite(value):
        result = value
    else:
        raise SelfDevelopmentEvidenceIntegrityError("Evidence contains an unsupported fact.")
    if isinstance(result, str):
        if len(result) > _MAX_STRING or _HOST_PATH.search(result):
            raise SelfDevelopmentEvidenceIntegrityError("Evidence contains unsafe content.")
    return result


def _facts(values: dict[str, object]) -> tuple[tuple[str, object], ...]:
    if len(values) > _MAX_FACTS:
        raise SelfDevelopmentEvidenceIntegrityError("Evidence facts are out of bounds.")
    return tuple((key, _safe_scalar(values[key])) for key in sorted(values))


@dataclass(frozen=True)
class ResolvedSelfDevelopmentEvidence:
    revision: str
    kind: str
    reference_id: str
    project_key: str
    source_created_at: str | None
    facts: tuple[tuple[str, object], ...]
    source_content_digest: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "kind": self.kind,
            "reference_id": self.reference_id,
            "project_key": self.project_key,
            "source_created_at": self.source_created_at,
            "facts": {key: value for key, value in self.facts},
            "source_content_digest": self.source_content_digest,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class SelfDevelopmentEvidenceResolution:
    revision: str
    project_key: str
    proposal_digest: str
    evidence: tuple[ResolvedSelfDevelopmentEvidence, ...]
    evidence_count: int
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {"revision": self.revision, "project_key": self.project_key, "proposal_digest": self.proposal_digest, "evidence": [item.to_dict() for item in self.evidence], "evidence_count": self.evidence_count, "digest": self.digest}


class SelfDevelopmentEvidenceResolver:
    def __init__(self, *, project_key: str, improvement_store: ImprovementStore, execution_receipt_store: ExecutionReceiptStore) -> None:
        if not isinstance(project_key, str) or not project_key or len(project_key) > 160:
            raise SelfDevelopmentEvidenceProjectError("Evidence project binding is invalid.")
        self.project_key = project_key
        self.improvement_store = improvement_store
        self.execution_receipt_store = execution_receipt_store

    async def _episode(self, reference_id: str) -> ResolvedSelfDevelopmentEvidence:
        try:
            row = await self.improvement_store.get_episode(reference_id, project_key=self.project_key)
        except KeyError as exc:
            raise SelfDevelopmentEvidenceNotFoundError("Evidence source was not found.") from exc
        for field in ("files_json", "evidence_json", "recalled_strategy_ids_json", "recalled_orientation_ids_json"):
            try:
                json.loads(row[field])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise SelfDevelopmentEvidenceIntegrityError("Evidence source is malformed.") from exc
        facts = _facts({"success": bool(row.get("success")), "failure_kind": row.get("failure_kind"), "created_at": row.get("created_at")})
        source_digest = _canonical(row)
        return self._item("experience_episode", reference_id, row.get("created_at"), facts, source_digest)

    async def _benchmark(self, reference_id: str) -> ResolvedSelfDevelopmentEvidence:
        try:
            row = await self.improvement_store.get_benchmark(reference_id, project_key=self.project_key)
        except KeyError as exc:
            raise SelfDevelopmentEvidenceNotFoundError("Evidence source was not found.") from exc
        try:
            details = json.loads(row["details_json"])
            score = float(row["score"])
            passed, total = int(row["passed"]), int(row["total"])
            if not math.isfinite(score) or passed < 0 or total < 0 or passed > total:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SelfDevelopmentEvidenceIntegrityError("Evidence source is malformed.") from exc
        facts = _facts({"candidate_id": row.get("candidate_id"), "score": score, "passed": passed, "total": total, "created_at": row.get("created_at")})
        source_digest = _canonical({"row": row, "details": details})
        return self._item("benchmark_run", reference_id, row.get("created_at"), facts, source_digest)

    async def _receipt(self, reference_id: str) -> ResolvedSelfDevelopmentEvidence:
        if reference_id.startswith("/") or reference_id.endswith("/") or reference_id.count("/") != 1 or "\\" in reference_id or ".." in reference_id:
            raise SelfDevelopmentEvidenceIntegrityError("Receipt reference syntax is invalid.")
        mission_id, receipt_id = reference_id.split("/")
        if not mission_id or not receipt_id or len(reference_id) > 160:
            raise SelfDevelopmentEvidenceIntegrityError("Receipt reference syntax is invalid.")
        try:
            receipt = self.execution_receipt_store.get_receipt(mission_id=mission_id, receipt_id=receipt_id)
        except ExecutionReceiptIntegrityError as exc:
            raise SelfDevelopmentEvidenceIntegrityError("Receipt integrity verification failed.") from exc
        if receipt is None:
            raise SelfDevelopmentEvidenceNotFoundError("Evidence source was not found.")
        safe = {key: getattr(receipt, key, None) for key in ("mission_id", "sequence", "execution_kind", "actor_kind", "outcome", "duration_ms", "exit_code", "receipt_hash", "input_hash", "result_hash")}
        facts = _facts(safe)
        source_digest = _canonical(receipt.model_dump(mode="json"))
        return self._item("execution_receipt", reference_id, None, facts, source_digest)

    @staticmethod
    def _item(kind: str, reference_id: str, created_at: object, facts: tuple[tuple[str, object], ...], source_digest: str) -> ResolvedSelfDevelopmentEvidence:
        created = _safe_scalar(created_at)
        if created is not None and not isinstance(created, str):
            raise SelfDevelopmentEvidenceIntegrityError("Evidence timestamp is invalid.")
        payload = {"revision": SELF_DEVELOPMENT_EVIDENCE_REVISION, "kind": kind, "reference_id": reference_id, "project_key": "", "source_created_at": created, "facts": dict(facts), "source_content_digest": source_digest}
        # project binding is inserted by resolve_reference before digest calculation.
        return ResolvedSelfDevelopmentEvidence(SELF_DEVELOPMENT_EVIDENCE_REVISION, kind, reference_id, "", created, facts, source_digest, _canonical(payload))

    async def resolve_reference(self, reference: SelfDevelopmentEvidenceReference) -> ResolvedSelfDevelopmentEvidence:
        if not isinstance(reference, SelfDevelopmentEvidenceReference) or reference.kind not in _EVIDENCE_KINDS or not isinstance(reference.reference_id, str) or not reference.reference_id.strip() or len(reference.reference_id) > 160 or not _SHA256.fullmatch(reference.digest):
            raise SelfDevelopmentEvidenceIntegrityError("Evidence reference is invalid.")
        if reference.kind == "experience_episode":
            item = await self._episode(reference.reference_id)
        elif reference.kind == "benchmark_run":
            item = await self._benchmark(reference.reference_id)
        else:
            item = await self._receipt(reference.reference_id)
        item = ResolvedSelfDevelopmentEvidence(item.revision, item.kind, item.reference_id, self.project_key, item.source_created_at, item.facts, item.source_content_digest, "")
        payload = item.to_dict(); payload.pop("digest")
        digest = _canonical(payload)
        if digest != reference.digest:
            raise SelfDevelopmentEvidenceIntegrityError("Evidence digest does not match.")
        return ResolvedSelfDevelopmentEvidence(item.revision, item.kind, item.reference_id, item.project_key, item.source_created_at, item.facts, item.source_content_digest, digest)

    async def build_reference(self, *, kind: str, reference_id: str) -> SelfDevelopmentEvidenceReference:
        if kind not in _EVIDENCE_KINDS:
            raise SelfDevelopmentEvidenceResolutionError("Evidence kind is invalid.")
        item = await self.resolve_unbound(kind, reference_id)
        bound = ResolvedSelfDevelopmentEvidence(item.revision, item.kind, item.reference_id, self.project_key, item.source_created_at, item.facts, item.source_content_digest, "")
        payload = bound.to_dict(); payload.pop("digest")
        return SelfDevelopmentEvidenceReference(kind, reference_id, _canonical(payload))

    async def resolve_unbound(self, kind: str, reference_id: str) -> ResolvedSelfDevelopmentEvidence:
        if kind == "experience_episode": return await self._episode(reference_id)
        if kind == "benchmark_run": return await self._benchmark(reference_id)
        if kind == "execution_receipt": return await self._receipt(reference_id)
        raise SelfDevelopmentEvidenceResolutionError("Evidence kind is invalid.")

    async def resolve_proposal(self, proposal: SelfDevelopmentProposalSnapshot) -> SelfDevelopmentEvidenceResolution:
        if not isinstance(proposal, SelfDevelopmentProposalSnapshot) or proposal.project_key != self.project_key or not _SHA256.fullmatch(proposal.digest):
            raise SelfDevelopmentEvidenceProjectError("Proposal project binding is invalid.")
        payload = proposal.to_dict(); digest = payload.pop("digest")
        if _canonical(payload) != digest:
            raise SelfDevelopmentEvidenceIntegrityError("Proposal digest is invalid.")
        resolved_items: list[ResolvedSelfDevelopmentEvidence] = []
        for reference in proposal.evidence:
            resolved_items.append(await self.resolve_reference(reference))
        items = tuple(sorted(resolved_items, key=lambda item: (item.kind, item.reference_id, item.digest)))
        aggregate_payload = {"revision": SELF_DEVELOPMENT_EVIDENCE_REVISION, "project_key": self.project_key, "proposal_digest": proposal.digest, "evidence": [item.to_dict() for item in items], "evidence_count": len(items)}
        return SelfDevelopmentEvidenceResolution(SELF_DEVELOPMENT_EVIDENCE_REVISION, self.project_key, proposal.digest, items, len(items), _canonical(aggregate_payload))
