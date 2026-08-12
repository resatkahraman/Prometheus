"""Canonical, fail-closed policy for events observed without a command.

This module calculates a ceiling only.  It does not execute actions or grant
any authority that a narrower capability/approval subsystem has not granted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
import hashlib
import json
from typing import Any, Iterable


PROACTIVE_POLICY_VERSION = "proactive-policy-v1"


class ProactiveActionLevel(IntEnum):
    OBSERVE_ONLY = 0
    SUGGEST_ACTION = 1
    PREPARE_PLAN = 2
    REQUEST_APPROVAL = 3
    EXECUTE_LOW_RISK = 4

    @property
    def value_name(self) -> str:
        return ("observe_only", "suggest_action", "prepare_plan", "request_approval", "execute_low_risk")[self.value]


_LEVELS = {level.value_name: level for level in ProactiveActionLevel}
_SOURCES = frozenset({"canonical_internal", "user_declared", "verified_connector", "untrusted_external", "model_inferred"})
_EVENT_TYPES = frozenset({
    "read_only_observation", "bounded_local_status_refresh", "local_metadata_bookkeeping",
    "safe_notification", "bounded_reversible_local_mutation", "action_requiring_confirmation",
    "prepare_bounded_plan", "request_approval", "destructive_file_deletion",
    "destructive_source_control", "credential_change", "authentication_change",
    "permission_escalation", "security_policy_change", "firewall_network_exposure",
    "remote_publication", "purchase", "payment", "financial_transaction",
    "irreversible_external_action", "private_data_disclosure", "message_as_user",
    "production_deployment", "git_push", "package_publication", "arbitrary_native_execution",
    "shell_execution", "self_development_promotion",
})

# Deliberately tiny.  The baseline has no narrow autonomous mutation capability
# that is safe to authorize here, so this remains empty until one is introduced.
LOW_RISK_EXECUTION_ALLOWLIST = frozenset()


def _canonical(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProactiveEvent:
    event_id: str
    event_type: str
    source_kind: str
    observed_at: datetime | None = None
    project_scope: str | None = None
    workspace_scope: str | None = None
    sensitivity: str | None = None
    reversibility: str | None = None
    external_side_effect: bool | None = None
    financial_effect: bool | None = None
    credential_or_permission_effect: bool | None = None
    destructive_effect: bool | None = None
    user_data_disclosure_effect: bool | None = None
    execution_capability_required: bool | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    model_context: str | None = None  # informational only; never policy input

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id is required")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("event_type is required")
        if not isinstance(self.source_kind, str) or not self.source_kind.strip():
            raise ValueError("source_kind is required")
        object.__setattr__(self, "event_id", self.event_id.strip())
        object.__setattr__(self, "event_type", self.event_type.strip())
        object.__setattr__(self, "source_kind", self.source_kind.strip())
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        for name in ("project_scope", "workspace_scope", "sensitivity", "reversibility", "model_context"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string or None")
        for name in ("external_side_effect", "financial_effect", "credential_or_permission_effect",
                     "destructive_effect", "user_data_disclosure_effect", "execution_capability_required"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean or None")
        if not isinstance(self.evidence_refs, (tuple, list)) or any(not isinstance(x, str) or not x.strip() for x in self.evidence_refs):
            raise ValueError("evidence_refs must contain non-empty strings")
        object.__setattr__(self, "evidence_refs", tuple(str(x) for x in self.evidence_refs))

    def trusted_payload(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "event_type": self.event_type, "source_kind": self.source_kind,
                "observed_at": self.observed_at.isoformat() if self.observed_at else None,
                "project_scope": self.project_scope, "workspace_scope": self.workspace_scope,
                "sensitivity": self.sensitivity, "reversibility": self.reversibility,
                "external_side_effect": self.external_side_effect, "financial_effect": self.financial_effect,
                "credential_or_permission_effect": self.credential_or_permission_effect,
                "destructive_effect": self.destructive_effect, "user_data_disclosure_effect": self.user_data_disclosure_effect,
                "execution_capability_required": self.execution_capability_required,
                "evidence_refs": list(self.evidence_refs)}


@dataclass(frozen=True)
class ProactivePolicyDecision:
    decision_id: str
    event_id: str
    maximum_action_level: str
    reasons: tuple[str, ...]
    required_approval: bool
    policy_version: str
    created_at: datetime
    deterministic_digest: str

    @property
    def digest(self) -> str:
        return self.deterministic_digest

    @property
    def action_level(self) -> str:
        return self.maximum_action_level

    def to_dict(self) -> dict[str, Any]:
        return {"decision_id": self.decision_id, "event_id": self.event_id, "maximum_action_level": self.maximum_action_level,
                "reasons": list(self.reasons), "required_approval": self.required_approval,
                "policy_version": self.policy_version, "created_at": self.created_at.isoformat(), "digest": self.digest}


def _missing(event: ProactiveEvent) -> list[str]:
    required = ("observed_at", "sensitivity", "reversibility", "external_side_effect", "financial_effect",
                "credential_or_permission_effect", "destructive_effect", "user_data_disclosure_effect",
                "execution_capability_required")
    return [name for name in required if getattr(event, name) is None]


def evaluate_proactive_event(event: ProactiveEvent, *, policy_version: str = PROACTIVE_POLICY_VERSION,
                             created_at: datetime | None = None, journal: Any | None = None,
                             mission_id: str | None = None) -> ProactivePolicyDecision:
    """Evaluate trusted structured facts.  Invalid/unknown facts observe only."""
    if not isinstance(event, ProactiveEvent):
        raise TypeError("event must be ProactiveEvent")
    reasons: list[str] = []
    level = ProactiveActionLevel.OBSERVE_ONLY
    missing = _missing(event)
    if missing:
        reasons.append("missing_required_metadata:" + ",".join(missing))
    elif event.event_type not in _EVENT_TYPES:
        reasons.append("unknown_event_type")
    elif event.source_kind not in _SOURCES:
        reasons.append("unknown_source_kind")
    elif event.source_kind in {"untrusted_external", "model_inferred"}:
        level = ProactiveActionLevel.SUGGEST_ACTION
        reasons.append("untrusted_or_model_inferred_source_cannot_authorize_execution")
    else:
        high = (event.external_side_effect or event.financial_effect or event.credential_or_permission_effect or
                event.destructive_effect or event.user_data_disclosure_effect or event.event_type in {
                    "destructive_file_deletion", "destructive_source_control", "credential_change", "authentication_change",
                    "permission_escalation", "security_policy_change", "firewall_network_exposure", "remote_publication",
                    "purchase", "payment", "financial_transaction", "irreversible_external_action", "private_data_disclosure",
                    "message_as_user", "production_deployment", "git_push", "package_publication", "arbitrary_native_execution",
                    "shell_execution", "self_development_promotion"})
        if high:
            level = ProactiveActionLevel.REQUEST_APPROVAL
            reasons.append("high_risk_requires_approval")
        elif event.event_type == "safe_notification":
            level = ProactiveActionLevel.SUGGEST_ACTION; reasons.append("bounded_user_facing_recommendation")
        elif event.event_type in {"prepare_bounded_plan", "bounded_reversible_local_mutation", "action_requiring_confirmation"}:
            level = ProactiveActionLevel.PREPARE_PLAN; reasons.append("bounded_non_executing_plan")
        elif event.event_type == "request_approval":
            level = ProactiveActionLevel.REQUEST_APPROVAL; reasons.append("explicit_approval_route")
        elif event.event_type in LOW_RISK_EXECUTION_ALLOWLIST and event.execution_capability_required is False:
            level = ProactiveActionLevel.EXECUTE_LOW_RISK; reasons.append("exact_low_risk_allowlist_match")
        else:
            reasons.append("read_only_or_no_explicit_execution_allowlist")
    if not reasons:
        reasons.append("fail_closed")
    payload = {"policy_version": policy_version, "event": event.trusted_payload(), "maximum_action_level": level.value_name,
               "reasons": reasons, "required_approval": level >= ProactiveActionLevel.REQUEST_APPROVAL}
    digest = _canonical(payload)
    decision_id = "ppd_" + digest[7:31]
    now = _utc(created_at) or datetime.now(timezone.utc)
    decision = ProactivePolicyDecision(decision_id, event.event_id, level.value_name, tuple(reasons), level >= ProactiveActionLevel.REQUEST_APPROVAL, policy_version, now, digest)
    if journal is not None and mission_id:
        existing = journal.list_events(mission_id=mission_id, limit=100000)
        if not any(ev.event_type == "proactive_policy_decided" and ev.payload.get("decision_id") == decision_id for ev in existing):
            journal.append(mission_id=mission_id, event_type="proactive_event_observed", actor="proactive_policy", payload={"event_id": event.event_id, "event_type": event.event_type})
            journal.append(mission_id=mission_id, event_type="proactive_policy_decided", actor="proactive_policy", payload={"event_id": event.event_id, "decision_id": decision_id, "maximum_action_level": level.value_name, "policy_version": policy_version, "decision_digest": digest})
    return decision


def effective_action_level(proactive_maximum: str, existing_capability_authority: str, existing_approval_authority: str) -> str:
    """Apply the narrowest downstream authority; invalid authority fails closed."""
    values = [ _LEVELS.get(value) for value in (proactive_maximum, existing_capability_authority, existing_approval_authority) ]
    if any(value is None for value in values):
        return ProactiveActionLevel.OBSERVE_ONLY.value_name
    return min(values).value_name  # type: ignore[arg-type]


def materialize_permitted_proactive_action(*args: Any, **kwargs: Any) -> None:
    """There is intentionally no generic proactive executor in TASK-073."""
    raise PermissionError("TASK-073 policy does not materialize or execute actions")
