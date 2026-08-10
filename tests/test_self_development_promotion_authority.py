from dataclasses import replace
import json
import pytest
from app.improvement.decision_gate import SelfDevelopmentDecisionGate
from app.improvement.human_decision import SelfDevelopmentHumanDecisionBinder
from app.improvement.promotion_authority import SelfDevelopmentPromotionAuthorityEligibilityError, SelfDevelopmentPromotionAuthorityIntegrityError, SelfDevelopmentPromotionAuthorityIssuer, SelfDevelopmentPromotionAuthorityProjectError
from tests.test_self_development_decision_gate import make_evaluation

@pytest.mark.asyncio
async def test_approved_authority_is_deterministic_and_non_mutating(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=evaluation)
    decision = SelfDevelopmentHumanDecisionBinder(project_key="project-a").bind(gate=gate, decision="approve")
    issuer = SelfDevelopmentPromotionAuthorityIssuer(project_key="project-a")
    first = issuer.issue(decision=decision)
    assert first == issuer.issue(decision=decision)
    assert first.authority_scope == "self-development-promotion" and first.promotion_authorized is True
    assert first.source_mutation_allowed is False and first.main_branch_mutation_allowed is False

@pytest.mark.asyncio
async def test_reject_mismatch_and_tampering_fail_closed(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=evaluation)
    binder = SelfDevelopmentHumanDecisionBinder(project_key="project-a")
    issuer = SelfDevelopmentPromotionAuthorityIssuer(project_key="project-a")
    reject = binder.bind(gate=gate, decision="reject")
    with pytest.raises(SelfDevelopmentPromotionAuthorityEligibilityError): issuer.issue(decision=reject)
    with pytest.raises(SelfDevelopmentPromotionAuthorityProjectError): SelfDevelopmentPromotionAuthorityIssuer(project_key="project-b").issue(decision=binder.bind(gate=gate, decision="approve"))
    with pytest.raises(SelfDevelopmentPromotionAuthorityIntegrityError): issuer.issue(decision=replace(binder.bind(gate=gate, decision="approve"), promotion_eligible=False))
    with pytest.raises(SelfDevelopmentPromotionAuthorityIntegrityError): issuer.issue(decision=replace(binder.bind(gate=gate, decision="approve"), human_approval_present=False))
    serialized = json.dumps(issuer.issue(decision=binder.bind(gate=gate, decision="approve")).to_dict())
    assert all(value not in serialized for value in ("C:\\secret-host-path", "RAW_EVALUATION_LOG_SECRET", "human rationale secret", "api_key=", "Bearer"))
