from dataclasses import replace
from pathlib import Path
import json
import pytest

from app.improvement.git_integration_approval import (
    SelfDevelopmentGitIntegrationApprovalBuilder,
    SelfDevelopmentGitIntegrationApprovalIntegrityError,
    SelfDevelopmentGitIntegrationApprovalStore,
)


def verification():
    from app.improvement.post_promotion_verification import SelfDevelopmentPostPromotionVerificationSnapshot, _canonical, _snapshot_payload
    item = SelfDevelopmentPostPromotionVerificationSnapshot("self-development-post-promotion-verification-v1", "sdpv_" + "a" * 24, "ws", "project", "sdpe_" + "b" * 24, "sha256:" + "1" * 64, "sdpb_" + "c" * 24, "sha256:" + "2" * 64, "sha256:" + "3" * 64, "sha256:" + "4" * 64, "sdpr_" + "d" * 24, "sha256:" + "5" * 64, "sha256:" + "6" * 64, 1, True, True, False, "sha256:" + "7" * 64)
    return replace(item, digest=_canonical(_snapshot_payload(item)))


def test_approval_is_deterministic_and_durable(tmp_path: Path):
    builder = SelfDevelopmentGitIntegrationApprovalBuilder(); first = builder.build(verification=verification(), project_key="project", workspace_path="ws", source_branch="task-xyz", expected_main_sha="a" * 40, decision="approve")
    second = builder.build(verification=verification(), project_key="project", workspace_path="ws", source_branch="task-xyz", expected_main_sha="a" * 40, decision="approve")
    assert first == second and first.local_git_integration_authorized and not first.remote_publication_authorized
    store = SelfDevelopmentGitIntegrationApprovalStore(root=tmp_path); store.append(first)
    fresh = SelfDevelopmentGitIntegrationApprovalStore(root=tmp_path)
    assert fresh.get_by_verification(verification_id=first.verification_id, verification_digest=first.verification_digest) == first


def test_rejected_approval_is_not_authorized():
    item = SelfDevelopmentGitIntegrationApprovalBuilder().build(verification=verification(), project_key="project", workspace_path="ws", source_branch="task-xyz", expected_main_sha="a" * 40, decision="reject")
    assert item.decision == "reject" and not item.local_git_integration_authorized and not item.remote_publication_authorized


def test_corrupt_store_fails_closed(tmp_path: Path):
    item = SelfDevelopmentGitIntegrationApprovalBuilder().build(verification=verification(), project_key="project", workspace_path="ws", source_branch="task-xyz", expected_main_sha="a" * 40, decision="approve")
    store = SelfDevelopmentGitIntegrationApprovalStore(root=tmp_path); store.append(item)
    path = next((tmp_path / "git_integration_approvals").glob("*.json")); data = json.loads(path.read_text(encoding="utf-8")); data["decision"] = "reject"; path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SelfDevelopmentGitIntegrationApprovalIntegrityError): store.get_by_verification(verification_id=item.verification_id, verification_digest=item.verification_digest)
