from dataclasses import replace
import json

import pytest

from app.improvement.candidate import SelfDevelopmentCandidateMaterializer
from app.improvement.evaluation import (
    SelfDevelopmentCandidateEvaluator,
    SelfDevelopmentEvaluationIntegrityError,
    SelfDevelopmentEvaluationObservation,
    SelfDevelopmentEvaluationProjectError,
    SelfDevelopmentEvaluationValidationError,
)
from tests.test_self_development_candidate import _inputs


def observation(check_id, outcome, suffix="a"):
    return SelfDevelopmentEvaluationObservation(check_id, outcome, "sha256:" + suffix * 64)


@pytest.mark.asyncio
async def _candidate(tmp_path):
    proposal, evidence = await _inputs(tmp_path)
    return SelfDevelopmentCandidateMaterializer(project_key="project-a").materialize(proposal=proposal, evidence=evidence)


@pytest.mark.asyncio
async def test_deterministic_evaluation_and_aggregation(tmp_path):
    candidate = await _candidate(tmp_path)
    evaluator = SelfDevelopmentCandidateEvaluator(project_key="project-a")
    observations = (observation("z-check", "pass", "b"), observation("a-check", "pass", "a"))
    first = evaluator.evaluate(candidate=candidate, observations=observations)
    second = evaluator.evaluate(candidate=candidate, observations=tuple(reversed(observations)))
    assert first == second
    assert first.overall_outcome == "pass"
    assert first.promotion_allowed is False
    assert first.requires_human_approval is True
    assert first.source_mutation_allowed is False
    assert first.main_branch_mutation_allowed is False


@pytest.mark.asyncio
async def test_fail_and_inconclusive_precedence(tmp_path):
    candidate = await _candidate(tmp_path)
    evaluator = SelfDevelopmentCandidateEvaluator(project_key="project-a")
    assert evaluator.evaluate(candidate=candidate, observations=(observation("a", "inconclusive"), observation("b", "fail", "b"))).overall_outcome == "fail"
    assert evaluator.evaluate(candidate=candidate, observations=(observation("a", "pass"), observation("b", "inconclusive", "b"))).overall_outcome == "inconclusive"


@pytest.mark.asyncio
async def test_invalid_observations_and_project_fail_closed(tmp_path):
    candidate = await _candidate(tmp_path)
    evaluator = SelfDevelopmentCandidateEvaluator(project_key="project-a")
    with pytest.raises(SelfDevelopmentEvaluationValidationError):
        evaluator.evaluate(candidate=candidate, observations=())
    with pytest.raises(SelfDevelopmentEvaluationValidationError):
        evaluator.evaluate(candidate=candidate, observations=(observation("a", "unknown"),))
    with pytest.raises(SelfDevelopmentEvaluationValidationError):
        evaluator.evaluate(candidate=candidate, observations=(SelfDevelopmentEvaluationObservation("a", "pass", "bad"),))
    with pytest.raises(SelfDevelopmentEvaluationValidationError):
        evaluator.evaluate(candidate=candidate, observations=(observation("a", "pass"), observation("a", "fail", "b")))
    with pytest.raises(SelfDevelopmentEvaluationProjectError):
        SelfDevelopmentCandidateEvaluator(project_key="project-b").evaluate(candidate=candidate, observations=(observation("a", "pass"),))


@pytest.mark.asyncio
async def test_candidate_corruption_and_unsafe_flags_rejected(tmp_path):
    candidate = await _candidate(tmp_path)
    evaluator = SelfDevelopmentCandidateEvaluator(project_key="project-a")
    with pytest.raises(SelfDevelopmentEvaluationIntegrityError):
        evaluator.evaluate(candidate=replace(candidate, candidate_kind="tampered"), observations=(observation("a", "pass"),))
    with pytest.raises(SelfDevelopmentEvaluationIntegrityError):
        evaluator.evaluate(candidate=replace(candidate, execution_allowed=True), observations=(observation("a", "pass"),))
    serialized = json.dumps(evaluator.evaluate(candidate=candidate, observations=(observation("a", "pass"),)).to_dict())
    assert "C:\\secret-host-path" not in serialized
    assert "RAW_EVALUATION_LOG_SECRET" not in serialized
    assert "api_key=" not in serialized
    assert "Bearer" not in serialized
