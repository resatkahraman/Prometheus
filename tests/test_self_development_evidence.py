import json
from dataclasses import replace

import pytest

from app.improvement.evidence import (
    SELF_DEVELOPMENT_EVIDENCE_REVISION,
    SelfDevelopmentEvidenceIntegrityError,
    SelfDevelopmentEvidenceNotFoundError,
    SelfDevelopmentEvidenceResolver,
)
from app.improvement.proposal import (
    SelfDevelopmentEvidenceReference,
    SelfDevelopmentEvidenceKind,
    SelfDevelopmentProposalBuilder,
    SelfDevelopmentProposalRequest,
)


class FakeImprovementStore:
    def __init__(self, episode=None, benchmark=None):
        self.episode = episode
        self.benchmark = benchmark

    async def get_episode(self, episode_id, *, project_key):
        if self.episode and self.episode["id"] == episode_id and self.episode["project_key"] == project_key:
            return dict(self.episode)
        raise KeyError(episode_id)

    async def get_benchmark(self, run_id, *, project_key):
        if self.benchmark and self.benchmark["id"] == run_id and self.benchmark["project_key"] == project_key:
            return dict(self.benchmark)
        raise KeyError(run_id)


class FakeReceiptStore:
    def __init__(self, receipt=None):
        self.receipt = receipt

    def get_receipt(self, *, mission_id, receipt_id):
        if self.receipt and self.receipt.mission_id == mission_id and self.receipt.receipt_id == receipt_id:
            return self.receipt
        return None


def episode(project="project-a"):
    return {"id": "episode-1", "project_key": project, "success": 1, "failure_kind": None, "created_at": "2026-01-01T00:00:00Z", "files_json": "[]", "evidence_json": "[]", "recalled_strategy_ids_json": "[]", "recalled_orientation_ids_json": "[]", "goal": "private goal", "title": "private title"}


def benchmark(project="project-a"):
    return {"id": "bench-1", "project_key": project, "candidate_id": "candidate-1", "score": 0.9, "passed": 9, "total": 10, "details_json": json.dumps({"private": "content"}), "created_at": "2026-01-01T00:00:00Z"}


@pytest.mark.asyncio
async def test_episode_build_reference_and_secret_safe_projection():
    resolver = SelfDevelopmentEvidenceResolver(project_key="project-a", improvement_store=FakeImprovementStore(episode=episode()), execution_receipt_store=FakeReceiptStore())
    reference = await resolver.build_reference(kind="experience_episode", reference_id="episode-1")
    resolved = await resolver.resolve_reference(reference)
    assert resolved.revision == SELF_DEVELOPMENT_EVIDENCE_REVISION
    assert dict(resolved.facts)["success"] is True
    assert "private goal" not in json.dumps(resolved.to_dict())


@pytest.mark.asyncio
async def test_benchmark_mismatch_and_cross_project_fail_closed():
    resolver = SelfDevelopmentEvidenceResolver(project_key="project-a", improvement_store=FakeImprovementStore(benchmark=benchmark("project-a")), execution_receipt_store=FakeReceiptStore())
    reference = await resolver.build_reference(kind="benchmark_run", reference_id="bench-1")
    with pytest.raises(SelfDevelopmentEvidenceIntegrityError):
        await resolver.resolve_reference(replace(reference, digest="sha256:" + "0" * 64))
    other = SelfDevelopmentEvidenceResolver(project_key="project-b", improvement_store=FakeImprovementStore(benchmark=benchmark("project-a")), execution_receipt_store=FakeReceiptStore())
    with pytest.raises(SelfDevelopmentEvidenceNotFoundError):
        await other.resolve_reference(reference)


@pytest.mark.asyncio
async def test_malformed_episode_json_is_rejected():
    row = episode()
    row["evidence_json"] = "{"
    resolver = SelfDevelopmentEvidenceResolver(project_key="project-a", improvement_store=FakeImprovementStore(episode=row), execution_receipt_store=FakeReceiptStore())
    with pytest.raises(SelfDevelopmentEvidenceIntegrityError):
        await resolver.build_reference(kind="experience_episode", reference_id="episode-1")


@pytest.mark.asyncio
async def test_proposal_resolution_is_deterministic_and_preserves_flags(tmp_path):
    store = FakeImprovementStore(episode=episode(), benchmark=benchmark())
    resolver = SelfDevelopmentEvidenceResolver(project_key="project-a", improvement_store=store, execution_receipt_store=FakeReceiptStore())
    refs = (await resolver.build_reference(kind="benchmark_run", reference_id="bench-1"), await resolver.build_reference(kind="experience_episode", reference_id="episode-1"))
    proposal = SelfDevelopmentProposalBuilder(project_root=tmp_path, workspace_path="ws", project_key="project-a").build(request=SelfDevelopmentProposalRequest("strategy", "Improve routing", "Evidence indicates a measurable reliability improvement.", "Reduce repeated failures.", refs))
    first = await resolver.resolve_proposal(proposal)
    second = await resolver.resolve_proposal(proposal)
    assert first.digest == second.digest
    assert first.evidence_count == 2
    assert proposal.proposal_only and not proposal.automatic_execution_allowed and not proposal.automatic_promotion_allowed and not proposal.main_branch_mutation_allowed
