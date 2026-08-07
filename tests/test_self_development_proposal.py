import hashlib

import pytest

from app.improvement.proposal import (
    SelfDevelopmentEvidenceReference,
    SelfDevelopmentProposalBuilder,
    SelfDevelopmentProposalEvidenceError,
    SelfDevelopmentProposalRequest,
    SelfDevelopmentProposalScopeError,
)
from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder


def evidence(reference="run-1"):
    return (SelfDevelopmentEvidenceReference("benchmark_run", reference, "sha256:" + "a" * 64),)


def request(kind="strategy", **kwargs):
    return SelfDevelopmentProposalRequest(kind, "Improve routing", "Evidence indicates a measurable reliability improvement.", "Reduce repeated failures.", evidence(), kwargs.get("target_paths", ()))


def test_logical_proposal_is_immutable_and_safe(tmp_path):
    snapshot = SelfDevelopmentProposalBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build(request=request())
    assert snapshot.revision == "self-development-proposal-v1"
    assert snapshot.proposal_only is True
    assert snapshot.automatic_execution_allowed is False
    assert snapshot.automatic_promotion_allowed is False
    assert snapshot.main_branch_mutation_allowed is False
    assert snapshot.repository_map_digest is None
    with pytest.raises((AttributeError, TypeError)):
        snapshot.title = "changed"


def test_evidence_is_required_and_canonical(tmp_path):
    builder = SelfDevelopmentProposalBuilder(project_root=tmp_path, workspace_path="ws", project_key="p")
    with pytest.raises(SelfDevelopmentProposalEvidenceError):
        builder.build(request=SelfDevelopmentProposalRequest("strategy", "Improve", "Evidence indicates a measurable improvement.", "Better results.", ()))
    first = SelfDevelopmentEvidenceReference("benchmark_run", "b", "sha256:" + "b" * 64)
    second = SelfDevelopmentEvidenceReference("experience_episode", "a", "sha256:" + "c" * 64)
    one = builder.build(request=SelfDevelopmentProposalRequest("strategy", "Improve", "Evidence indicates a measurable improvement.", "Better results.", (first, second)))
    two = builder.build(request=SelfDevelopmentProposalRequest("strategy", "Improve", "Evidence indicates a measurable improvement.", "Better results.", (second, first)))
    assert one.evidence == two.evidence and one.digest == two.digest


def test_source_patch_binds_map_scope_and_targets(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    repo = RepositoryMapBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build()
    lock = ScopeLockBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build(repository_map=repo, allowed_write_paths=["a.py"])
    snapshot = SelfDevelopmentProposalBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build(request=request("source_patch", target_paths=("a.py",)), repository_map=repo, scope_lock=lock)
    assert snapshot.target_paths == ("a.py",)
    assert snapshot.repository_map_digest == repo.digest
    assert snapshot.scope_lock_digest == lock.snapshot.digest
    assert "x = 1" not in str(snapshot.to_dict())


def test_source_patch_requires_authorized_existing_source(tmp_path):
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")
    repo = RepositoryMapBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build()
    lock = ScopeLockBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build(repository_map=repo, allowed_write_paths=["README.md"])
    with pytest.raises(SelfDevelopmentProposalScopeError):
        SelfDevelopmentProposalBuilder(project_root=tmp_path, workspace_path="ws", project_key="p").build(request=request("source_patch", target_paths=("README.md",)), repository_map=repo, scope_lock=lock)


def test_proposal_digest_changes_with_rationale(tmp_path):
    builder = SelfDevelopmentProposalBuilder(project_root=tmp_path, workspace_path="ws", project_key="p")
    first = builder.build(request=request())
    changed = SelfDevelopmentProposalRequest("strategy", "Improve routing", "Evidence indicates a different measurable improvement.", "Reduce repeated failures.", evidence())
    assert first.digest != builder.build(request=changed).digest
