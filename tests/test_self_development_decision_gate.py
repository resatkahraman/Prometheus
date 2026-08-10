from dataclasses import replace
import json

import pytest

from app.improvement.decision_gate import SelfDevelopmentDecisionGate, SelfDevelopmentDecisionGateIntegrityError, SelfDevelopmentDecisionGateProjectError
from app.improvement.evaluation import SelfDevelopmentCandidateEvaluator, SelfDevelopmentEvaluationObservation
from tests.test_self_development_candidate import _inputs


async def make_evaluation(tmp_path, outcome="pass"):
    proposal, evidence = await _inputs(tmp_path)
    from app.improvement.candidate import SelfDevelopmentCandidateMaterializer
    candidate = SelfDevelopmentCandidateMaterializer(project_key="project-a").materialize(proposal=proposal, evidence=evidence)
    return SelfDevelopmentCandidateEvaluator(project_key="project-a").evaluate(candidate=candidate, observations=(SelfDevelopmentEvaluationObservation("check", outcome, "sha256:" + "a" * 64),))


@pytest.mark.asyncio
async def test_deterministic_pass_gate_and_safety(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a")
    assert gate.decide(evaluation=evaluation) == gate.decide(evaluation=evaluation)
    snapshot = gate.decide(evaluation=evaluation)
    assert snapshot.gate_status == "review_required"
    assert snapshot.eligible_for_human_review is True
    assert snapshot.requires_human_approval is True
    assert snapshot.promotion_allowed is False
    assert snapshot.source_mutation_allowed is False
    assert snapshot.main_branch_mutation_allowed is False


@pytest.mark.asyncio
async def test_failed_and_inconclusive_evaluations_block(tmp_path):
    gate = SelfDevelopmentDecisionGate(project_key="project-a")
    failed = gate.decide(evaluation=await make_evaluation(tmp_path, "fail"))
    inconclusive = gate.decide(evaluation=await make_evaluation(tmp_path, "inconclusive"))
    assert failed.gate_status == "blocked_failed" and not failed.eligible_for_human_review
    assert inconclusive.gate_status == "blocked_inconclusive" and not inconclusive.eligible_for_human_review


@pytest.mark.asyncio
async def test_integrity_project_and_serialization_guards(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a")
    with pytest.raises(SelfDevelopmentDecisionGateProjectError):
        SelfDevelopmentDecisionGate(project_key="project-b").decide(evaluation=evaluation)
    with pytest.raises(SelfDevelopmentDecisionGateIntegrityError):
        gate.decide(evaluation=replace(evaluation, promotion_allowed=True))
    with pytest.raises(SelfDevelopmentDecisionGateIntegrityError):
        gate.decide(evaluation=replace(evaluation, overall_outcome="fail"))
    serialized = json.dumps(gate.decide(evaluation=evaluation).to_dict())
    assert "C:\\secret-host-path" not in serialized and "RAW_EVALUATION_LOG_SECRET" not in serialized
    assert "api_key=" not in serialized and "Bearer" not in serialized
