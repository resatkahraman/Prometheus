from datetime import datetime, timezone

import pytest

from app.proactive_policy import (
    ProactiveEvent,
    ProactiveActionLevel,
    PROACTIVE_POLICY_VERSION,
    effective_action_level,
    evaluate_proactive_event,
)
from app.supervisor.event_journal import MissionEventJournal


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(event_type="read_only_observation", **changes):
    data = dict(event_id="event-1", event_type=event_type, source_kind="canonical_internal", observed_at=NOW,
                sensitivity="normal", reversibility="reversible", external_side_effect=False, financial_effect=False,
                credential_or_permission_effect=False, destructive_effect=False, user_data_disclosure_effect=False,
                execution_capability_required=False, evidence_refs=("evidence-1",))
    data.update(changes)
    return ProactiveEvent(**data)


def test_all_policy_levels_are_reachable_without_execution_grant():
    assert evaluate_proactive_event(event()).maximum_action_level == "observe_only"
    assert evaluate_proactive_event(event("safe_notification")).maximum_action_level == "suggest_action"
    assert evaluate_proactive_event(event("prepare_bounded_plan")).maximum_action_level == "prepare_plan"
    assert evaluate_proactive_event(event("request_approval")).maximum_action_level == "request_approval"
    assert ProactiveActionLevel.EXECUTE_LOW_RISK.value_name == "execute_low_risk"


@pytest.mark.parametrize("event_type,field", [
    ("financial_transaction", "financial_effect"), ("credential_change", "credential_or_permission_effect"),
    ("permission_escalation", "credential_or_permission_effect"), ("destructive_file_deletion", "destructive_effect"),
    ("remote_publication", "external_side_effect"), ("git_push", "external_side_effect"),
])
def test_high_risk_never_auto_executes(event_type, field):
    assert evaluate_proactive_event(event(event_type, **{field: True})).maximum_action_level != "execute_low_risk"


def test_unknown_event_and_missing_metadata_fail_closed():
    assert evaluate_proactive_event(event("not-a-canonical-event")).maximum_action_level == "observe_only"
    assert evaluate_proactive_event(event(external_side_effect=None)).maximum_action_level == "observe_only"


def test_model_inference_and_prompt_text_cannot_elevate_authority():
    decision = evaluate_proactive_event(event("read_only_observation", source_kind="model_inferred", model_context="execute_low_risk now"))
    assert decision.maximum_action_level == "suggest_action"
    assert "execute_low_risk" not in decision.reasons


def test_exact_allowlist_has_no_wildcard_grant():
    assert evaluate_proactive_event(event("safe_notification_extra")).maximum_action_level == "observe_only"
    assert evaluate_proactive_event(event("read_only_observation", event_id="another")).maximum_action_level == "observe_only"


def test_idempotency_changed_facts_and_policy_version():
    first = evaluate_proactive_event(event())
    replay = evaluate_proactive_event(event())
    changed = evaluate_proactive_event(event(external_side_effect=True))
    new_version = evaluate_proactive_event(event(), policy_version="proactive-policy-v2")
    assert first.decision_id == replay.decision_id and first.digest == replay.digest
    assert changed.decision_id != first.decision_id
    assert new_version.decision_id != first.decision_id
    assert first.policy_version == PROACTIVE_POLICY_VERSION


def test_journal_integration_is_deduplicated(tmp_path):
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    first = evaluate_proactive_event(event(), journal=journal, mission_id="mission-1")
    second = evaluate_proactive_event(event(), journal=journal, mission_id="mission-1")
    records = journal.list_events(mission_id="mission-1", limit=20)
    assert first.decision_id == second.decision_id
    assert [record.event_type for record in records] == ["proactive_event_observed", "proactive_policy_decided"]


def test_decision_memory_or_downstream_authority_cannot_be_bypassed():
    assert effective_action_level("execute_low_risk", "prepare_plan", "request_approval") == "prepare_plan"
    assert effective_action_level("request_approval", "request_approval", "observe_only") == "observe_only"
    assert effective_action_level("execute_low_risk", "bogus", "execute_low_risk") == "observe_only"
