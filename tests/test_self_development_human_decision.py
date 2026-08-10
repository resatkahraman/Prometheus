from dataclasses import replace
import json
import pytest
from app.improvement.decision_gate import SelfDevelopmentDecisionGate
from app.improvement.human_decision import SelfDevelopmentHumanDecisionBinder, SelfDevelopmentHumanDecisionEligibilityError, SelfDevelopmentHumanDecisionIntegrityError, SelfDevelopmentHumanDecisionProjectError, SelfDevelopmentHumanDecisionValidationError
from tests.test_self_development_decision_gate import make_evaluation

@pytest.mark.asyncio
async def test_approve_reject_deterministic(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=evaluation)
    binder = SelfDevelopmentHumanDecisionBinder(project_key="project-a")
    approve = binder.bind(gate=gate, decision="approve")
    assert approve == binder.bind(gate=gate, decision="approve")
    reject = binder.bind(gate=gate, decision="reject")
    assert approve.decision_id != reject.decision_id and approve.digest != reject.digest
    assert approve.human_approval_present and approve.promotion_eligible and not approve.source_mutation_allowed and not approve.main_branch_mutation_allowed
    assert reject.human_approval_present and not reject.promotion_eligible

@pytest.mark.asyncio
async def test_blocked_and_invalid_decisions_fail_closed(tmp_path):
    binder = SelfDevelopmentHumanDecisionBinder(project_key="project-a")
    for outcome in ("fail", "inconclusive"):
        gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=await make_evaluation(tmp_path, outcome))
        with pytest.raises(SelfDevelopmentHumanDecisionEligibilityError): binder.bind(gate=gate, decision="approve")
        with pytest.raises(SelfDevelopmentHumanDecisionEligibilityError): binder.bind(gate=gate, decision="reject")
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=await make_evaluation(tmp_path))
    for value in ("approved", "yes", "no", "allow", "deny", "pending", ""):
        with pytest.raises(SelfDevelopmentHumanDecisionValidationError): binder.bind(gate=gate, decision=value)

@pytest.mark.asyncio
async def test_gate_integrity_project_and_safe_serialization(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=evaluation)
    binder = SelfDevelopmentHumanDecisionBinder(project_key="project-a")
    with pytest.raises(SelfDevelopmentHumanDecisionProjectError): SelfDevelopmentHumanDecisionBinder(project_key="project-b").bind(gate=gate, decision="approve")
    with pytest.raises(SelfDevelopmentHumanDecisionIntegrityError): binder.bind(gate=replace(gate, promotion_allowed=True), decision="approve")
    with pytest.raises(SelfDevelopmentHumanDecisionIntegrityError): binder.bind(gate=replace(gate, eligible_for_human_review=False), decision="approve")
    serialized = json.dumps(binder.bind(gate=gate, decision="approve").to_dict())
    assert all(value not in serialized for value in ("C:\\secret-host-path", "RAW_EVALUATION_LOG_SECRET", "api_key=", "Bearer", "human rationale secret"))
