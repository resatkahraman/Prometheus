import json
from dataclasses import replace

import pytest

from app.improvement.candidate import (
    SELF_DEVELOPMENT_CANDIDATE_REVISION,
    SelfDevelopmentCandidateIntegrityError,
    SelfDevelopmentCandidateMaterializer,
    SelfDevelopmentCandidateProjectError,
)
from app.improvement.evidence import (
    SelfDevelopmentEvidenceResolver,
)
from app.improvement.proposal import (
    SelfDevelopmentProposalBuilder,
    SelfDevelopmentProposalRequest,
)
from tests.test_self_development_evidence import FakeImprovementStore, FakeReceiptStore, benchmark, episode


@pytest.mark.asyncio
async def _inputs(tmp_path, project="project-a"):
    resolver = SelfDevelopmentEvidenceResolver(
        project_key=project,
        improvement_store=FakeImprovementStore(episode=episode(project), benchmark=benchmark(project)),
        execution_receipt_store=FakeReceiptStore(),
    )
    refs = (
        await resolver.build_reference(kind="benchmark_run", reference_id="bench-1"),
        await resolver.build_reference(kind="experience_episode", reference_id="episode-1"),
    )
    proposal = SelfDevelopmentProposalBuilder(
        project_root=tmp_path, workspace_path="ws", project_key=project
    ).build(
        request=SelfDevelopmentProposalRequest(
            "strategy", "Improve routing", "Evidence indicates a measurable reliability improvement.",
            "Reduce repeated failures.", refs,
        )
    )
    return proposal, await resolver.resolve_proposal(proposal)


@pytest.mark.asyncio
async def test_materialization_is_deterministic_and_safe(tmp_path):
    proposal, evidence = await _inputs(tmp_path)
    first = SelfDevelopmentCandidateMaterializer(project_key="project-a").materialize(proposal=proposal, evidence=evidence)
    second = SelfDevelopmentCandidateMaterializer(project_key="project-a").materialize(proposal=proposal, evidence=evidence)
    assert first == second
    assert first.revision == SELF_DEVELOPMENT_CANDIDATE_REVISION
    assert first.candidate_id == second.candidate_id
    assert first.digest == second.digest
    assert first.requires_human_approval is True
    assert first.execution_allowed is False
    assert first.source_mutation_allowed is False
    assert first.main_branch_mutation_allowed is False
    assert first.evidence_item_digests == tuple(sorted(first.evidence_item_digests))


@pytest.mark.asyncio
async def test_binding_and_corruption_fail_closed(tmp_path):
    proposal, evidence = await _inputs(tmp_path)
    materializer = SelfDevelopmentCandidateMaterializer(project_key="project-a")
    with pytest.raises(SelfDevelopmentCandidateIntegrityError):
        materializer.materialize(proposal=proposal, evidence=replace(evidence, proposal_digest="sha256:" + "0" * 64))
    with pytest.raises(SelfDevelopmentCandidateProjectError):
        SelfDevelopmentCandidateMaterializer(project_key="project-b").materialize(proposal=proposal, evidence=evidence)
    with pytest.raises(SelfDevelopmentCandidateIntegrityError):
        materializer.materialize(proposal=replace(proposal, title="tampered"), evidence=evidence)
    with pytest.raises(SelfDevelopmentCandidateIntegrityError):
        materializer.materialize(proposal=proposal, evidence=replace(evidence, digest="sha256:" + "0" * 64))


@pytest.mark.asyncio
async def test_serialized_candidate_is_bounded_and_secret_safe(tmp_path):
    proposal, evidence = await _inputs(tmp_path)
    candidate = SelfDevelopmentCandidateMaterializer(project_key="project-a").materialize(proposal=proposal, evidence=evidence)
    serialized = json.dumps(candidate.to_dict())
    assert str(tmp_path) not in serialized
    assert "private goal" not in serialized
    assert "private title" not in serialized
    assert "private" not in serialized
