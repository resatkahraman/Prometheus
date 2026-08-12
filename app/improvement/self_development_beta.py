"""Bounded orchestration contract for the supervised self-development beta.

This module coordinates identities owned by TASK-059..071. It deliberately
contains no proposal engine, executor, process launcher or Git implementation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

BETA_VERSION = "SELF_DEVELOPMENT_BETA_V1"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,159}$")
_RISK = frozenset({"low", "medium"})
_BLOCKED_TERMS = frozenset({
    "security", "credential", "authentication", "authorization", "permission",
    "password", "secret", "token", "remote", "publish", "deploy", "installer",
    "pandora", "desktop native", "shell", "power" + "shell", "process", "git " + "push",
    "rewrite prometheus", "optimize everything", "change security",
})


class BetaError(ValueError):
    """Base error for invalid or corrupt beta state."""


class BetaValidationError(BetaError):
    pass


class BetaIntegrityError(BetaError):
    pass


class BetaScopeError(BetaError):
    pass


class BetaPhase(str, Enum):
    REQUESTED = "requested"
    PROPOSAL_READY = "proposal_ready"
    EVIDENCE_READY = "evidence_ready"
    CANDIDATE_READY = "candidate_ready"
    EVALUATION_READY = "evaluation_ready"
    DECISION_REQUIRED = "decision_required"
    PROMOTION_APPROVAL_REQUIRED = "promotion_approval_required"
    PROMOTION_READY = "promotion_ready"
    PROMOTION_EXECUTED = "promotion_executed"
    POST_PROMOTION_VERIFIED = "post_promotion_verified"
    GIT_APPROVAL_REQUIRED = "git_approval_required"
    GIT_INTEGRATION_READY = "git_integration_ready"
    GIT_INTEGRATED = "git_integrated"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"


_TERMINAL = frozenset({BetaPhase.COMPLETED, BetaPhase.BLOCKED, BetaPhase.RECOVERY_REQUIRED, BetaPhase.FAILED})
_ARTIFACT_FIELDS = {
    BetaPhase.PROPOSAL_READY: "proposal_id", BetaPhase.EVIDENCE_READY: "evidence_resolution_id",
    BetaPhase.CANDIDATE_READY: "candidate_id", BetaPhase.EVALUATION_READY: "evaluation_id",
    BetaPhase.DECISION_REQUIRED: "decision_id", BetaPhase.PROMOTION_APPROVAL_REQUIRED: "promotion_binding_id",
    BetaPhase.PROMOTION_READY: "promotion_binding_id", BetaPhase.PROMOTION_EXECUTED: "execution_receipt_id",
    BetaPhase.POST_PROMOTION_VERIFIED: "verification_id", BetaPhase.GIT_APPROVAL_REQUIRED: "git_approval_id",
    BetaPhase.GIT_INTEGRATION_READY: "git_approval_id", BetaPhase.GIT_INTEGRATED: "git_integration_receipt_id",
}
_NEXT = {
    BetaPhase.REQUESTED: BetaPhase.PROPOSAL_READY,
    BetaPhase.PROPOSAL_READY: BetaPhase.EVIDENCE_READY,
    BetaPhase.EVIDENCE_READY: BetaPhase.CANDIDATE_READY,
    BetaPhase.CANDIDATE_READY: BetaPhase.EVALUATION_READY,
    BetaPhase.EVALUATION_READY: BetaPhase.DECISION_REQUIRED,
    BetaPhase.DECISION_REQUIRED: BetaPhase.PROMOTION_APPROVAL_REQUIRED,
    BetaPhase.PROMOTION_APPROVAL_REQUIRED: BetaPhase.PROMOTION_READY,
    BetaPhase.PROMOTION_READY: BetaPhase.PROMOTION_EXECUTED,
    BetaPhase.PROMOTION_EXECUTED: BetaPhase.POST_PROMOTION_VERIFIED,
    BetaPhase.POST_PROMOTION_VERIFIED: BetaPhase.GIT_APPROVAL_REQUIRED,
    BetaPhase.GIT_APPROVAL_REQUIRED: BetaPhase.GIT_INTEGRATION_READY,
    BetaPhase.GIT_INTEGRATION_READY: BetaPhase.GIT_INTEGRATED,
    BetaPhase.GIT_INTEGRATED: BetaPhase.COMPLETED,
}


def _canonical(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value.strip()):
        raise BetaValidationError(f"Beta {name} is invalid.")
    return value.strip()


def _clean_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise BetaIntegrityError(f"Beta {name} digest is invalid.")
    return value


@dataclass(frozen=True)
class SelfDevelopmentBetaRequest:
    request_id: str
    workspace_path: str
    project_key: str
    objective: str
    trusted_objective_source: str
    context_refs: tuple[str, ...]
    maximum_scope: tuple[str, ...]
    requested_risk_class: str
    created_at: str
    beta_version: str = BETA_VERSION
    digest: str = ""

    def __post_init__(self) -> None:
        request_id = _clean_id(self.request_id, "request id")
        if self.beta_version != BETA_VERSION:
            raise BetaValidationError("Unsupported self-development beta version.")
        if not isinstance(self.workspace_path, str) or not Path(self.workspace_path).is_absolute() or ".." in Path(self.workspace_path).parts:
            raise BetaScopeError("Beta workspace must be one canonical absolute path.")
        if not isinstance(self.project_key, str) or not self.project_key.strip() or len(self.project_key) > 160:
            raise BetaScopeError("Beta project scope is invalid.")
        objective = self.objective.strip() if isinstance(self.objective, str) else ""
        if not 8 <= len(objective) <= 1000 or "\x00" in objective:
            raise BetaValidationError("Beta objective is invalid.")
        lowered = objective.casefold()
        if any(term in lowered for term in _BLOCKED_TERMS):
            raise BetaScopeError("Beta objective requires a higher authority path.")
        if self.requested_risk_class not in _RISK:
            raise BetaValidationError("Beta risk class is invalid.")
        source = self.trusted_objective_source.strip() if isinstance(self.trusted_objective_source, str) else ""
        if not source or source.casefold() in {"model", "llm", "assistant"}:
            raise BetaValidationError("Beta objective source must be trusted.")
        refs = tuple(self.context_refs)
        scope = tuple(self.maximum_scope)
        if not refs or len(refs) > 32 or any(not isinstance(v, str) or not v.strip() for v in refs):
            raise BetaValidationError("Beta context references are invalid.")
        if not scope or len(scope) > 32 or any(not isinstance(v, str) or not v.strip() or Path(v).is_absolute() or ".." in Path(v).parts for v in scope):
            raise BetaScopeError("Beta maximum scope is invalid.")
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            raise BetaValidationError("Beta creation time is invalid.")
        payload = self.to_dict(include_digest=False)
        expected = _canonical(payload)
        if self.digest and self.digest != expected:
            raise BetaIntegrityError("Beta request digest is invalid.")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "digest", expected)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        value = {"request_id": self.request_id, "workspace_path": self.workspace_path, "project_key": self.project_key, "objective": self.objective, "trusted_objective_source": self.trusted_objective_source, "context_refs": list(self.context_refs), "maximum_scope": list(self.maximum_scope), "requested_risk_class": self.requested_risk_class, "created_at": self.created_at, "beta_version": self.beta_version}
        if include_digest:
            value["digest"] = self.digest
        return value


@dataclass(frozen=True)
class SelfDevelopmentBetaResult:
    beta_run_id: str
    request_id: str
    request_digest: str
    workspace_path: str
    project_key: str
    phase: BetaPhase
    status: str
    proposal_id: str | None = None
    evidence_resolution_id: str | None = None
    candidate_id: str | None = None
    evaluation_id: str | None = None
    decision_id: str | None = None
    promotion_binding_id: str | None = None
    execution_receipt_id: str | None = None
    verification_id: str | None = None
    git_approval_id: str | None = None
    git_integration_receipt_id: str | None = None
    blocked_reason: str | None = None
    required_next_authority: str | None = None
    created_at: str = ""
    updated_at: str = ""
    beta_version: str = BETA_VERSION
    digest: str = ""

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        value = {name: (getattr(self, name).value if name == "phase" else getattr(self, name)) for name in self.__dataclass_fields__ if name != "digest"}
        if include_digest:
            value["digest"] = self.digest
        return value


class SelfDevelopmentBetaStore:
    """Durable beta state store; it stores orchestration state, never source."""
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.root / (hashlib.sha256(run_id.encode("utf-8")).hexdigest() + ".json")

    def save(self, result: SelfDevelopmentBetaResult) -> SelfDevelopmentBetaResult:
        payload = result.to_dict(include_digest=False)
        digest = _canonical(payload)
        stored = replace(result, digest=digest)
        self._path(stored.beta_run_id).write_bytes(json.dumps(stored.to_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8"))
        return stored

    def load(self, run_id: str) -> SelfDevelopmentBetaResult:
        path = self._path(_clean_id(run_id, "run id"))
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
            digest = data.pop("digest")
            result = SelfDevelopmentBetaResult(**{**data, "phase": BetaPhase(data["phase"]), "digest": digest})
        except FileNotFoundError:
            raise BetaValidationError("Beta run was not found.") from None
        except Exception as exc:
            raise BetaIntegrityError("Beta durable state is corrupt.") from exc
        if _canonical(result.to_dict(include_digest=False)) != result.digest:
            raise BetaIntegrityError("Beta durable state digest is invalid.")
        return result


class SelfDevelopmentBetaOrchestrator:
    """Explicit coordinator around the existing self-development authority chain."""
    def __init__(self, *, store: SelfDevelopmentBetaStore, journal: Any | None = None) -> None:
        self.store, self.journal = store, journal

    def _emit(self, result: SelfDevelopmentBetaResult, event_type: str) -> None:
        if self.journal is not None:
            self.journal.append(mission_id=result.beta_run_id, event_type=event_type, payload={"phase": result.phase.value, "status": result.status})

    def start(self, request: SelfDevelopmentBetaRequest) -> SelfDevelopmentBetaResult:
        if not isinstance(request, SelfDevelopmentBetaRequest):
            raise BetaValidationError("Beta request is invalid.")
        run_id = "sdb_" + _canonical({"version": BETA_VERSION, "request_id": request.request_id, "request_digest": request.digest})[7:31]
        try:
            existing = self.store.load(run_id)
            if existing.request_digest != request.digest:
                raise BetaIntegrityError("Beta request identity conflict.")
            return existing
        except BetaValidationError:
            pass
        now = _now()
        result = SelfDevelopmentBetaResult(run_id, request.request_id, request.digest, request.workspace_path, request.project_key, BetaPhase.REQUESTED, "awaiting_proposal", created_at=now, updated_at=now)
        result = self.store.save(result)
        self._emit(result, "self_development_beta_requested")
        return result

    def get(self, beta_run_id: str) -> SelfDevelopmentBetaResult:
        return self.store.load(beta_run_id)

    def resume(self, beta_run_id: str) -> SelfDevelopmentBetaResult:
        result = self.store.load(beta_run_id)
        if result.phase in _TERMINAL:
            return result
        return result

    def _record(self, run_id: str, phase: BetaPhase, artifact_id: str | None, *, status: str, blocked_reason: str | None = None, required_next_authority: str | None = None) -> SelfDevelopmentBetaResult:
        current = self.store.load(run_id)
        if current.phase in _TERMINAL:
            return current
        expected = _NEXT.get(current.phase)
        if expected != phase:
            raise BetaValidationError(f"Invalid beta transition from {current.phase.value} to {phase.value}.")
        field = "decision_id" if phase is BetaPhase.PROMOTION_APPROVAL_REQUIRED else _ARTIFACT_FIELDS.get(phase)
        if field and artifact_id is not None:
            _clean_id(artifact_id, field)
        if phase in {BetaPhase.DECISION_REQUIRED, BetaPhase.PROMOTION_APPROVAL_REQUIRED, BetaPhase.GIT_APPROVAL_REQUIRED} and not artifact_id:
            status = "blocked"
            blocked_reason = blocked_reason or "Required human authority is not present."
            required_next_authority = required_next_authority or phase.value
        kwargs = {field: artifact_id} if field and artifact_id else {}
        updated = replace(current, phase=phase, status=status, updated_at=_now(), blocked_reason=blocked_reason, required_next_authority=required_next_authority, **kwargs)
        updated = self.store.save(updated)
        self._emit(updated, "self_development_beta_phase_changed" if status != "blocked" else "self_development_beta_blocked")
        return updated

    def record_proposal(self, run_id: str, proposal_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.PROPOSAL_READY, proposal_id, status="proposal_ready")
    def record_evidence(self, run_id: str, evidence_resolution_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.EVIDENCE_READY, evidence_resolution_id, status="evidence_ready")
    def record_candidate(self, run_id: str, candidate_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.CANDIDATE_READY, candidate_id, status="candidate_ready")
    def record_evaluation(self, run_id: str, evaluation_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.EVALUATION_READY, evaluation_id, status="evaluation_ready")
    def require_decision(self, run_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.DECISION_REQUIRED, None, status="blocked", required_next_authority="TASK-064 human decision")
    def record_decision(self, run_id: str, decision_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.PROMOTION_APPROVAL_REQUIRED, decision_id, status="blocked", required_next_authority="TASK-066 approved binding")
    def record_promotion_binding(self, run_id: str, binding_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.PROMOTION_READY, binding_id, status="promotion_ready")
    def record_execution(self, run_id: str, receipt_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.PROMOTION_EXECUTED, receipt_id, status="promotion_executed")
    def record_verification(self, run_id: str, verification_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.POST_PROMOTION_VERIFIED, verification_id, status="post_promotion_verified")
    def require_git_approval(self, run_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.GIT_APPROVAL_REQUIRED, None, status="blocked", required_next_authority="TASK-070 Git integration approval")
    def record_git_approval(self, run_id: str, approval_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.GIT_INTEGRATION_READY, approval_id, status="git_integration_ready")
    def record_git_integration(self, run_id: str, receipt_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.GIT_INTEGRATED, receipt_id, status="git_integrated")
    def complete(self, run_id: str) -> SelfDevelopmentBetaResult: return self._record(run_id, BetaPhase.COMPLETED, None, status="completed")


def start_self_development_beta(orchestrator: SelfDevelopmentBetaOrchestrator, request: SelfDevelopmentBetaRequest) -> SelfDevelopmentBetaResult:
    """Explicit invocation boundary; beta mode is never enabled implicitly."""
    return orchestrator.start(request)


def resume_self_development_beta(orchestrator: SelfDevelopmentBetaOrchestrator, beta_run_id: str) -> SelfDevelopmentBetaResult:
    return orchestrator.resume(beta_run_id)


def get_self_development_beta(orchestrator: SelfDevelopmentBetaOrchestrator, beta_run_id: str) -> SelfDevelopmentBetaResult:
    return orchestrator.get(beta_run_id)
