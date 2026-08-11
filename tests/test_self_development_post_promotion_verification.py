from dataclasses import replace
from pathlib import Path
import json
import pytest

from app.improvement.post_promotion_verification import (
    SelfDevelopmentPostPromotionVerificationIntegrityError,
    SelfDevelopmentPostPromotionVerificationSnapshot,
    SelfDevelopmentPostPromotionVerificationStore,
    _canonical,
    _snapshot_payload,
)


def snapshot(**changes):
    base = dict(revision="self-development-post-promotion-verification-v1", verification_id="", workspace_path="workspace", project_key="project", execution_id="sdpe_" + "a" * 24, execution_digest="sha256:" + "b" * 64, binding_id="sdpb_" + "c" * 24, binding_digest="sha256:" + "d" * 64, plan_digest="sha256:" + "e" * 64, change_payload_digest="sha256:" + "f" * 64, promotion_receipt_id="sdpr_" + "1" * 24, promotion_receipt_digest="sha256:" + "1" * 64, verified_state_digest="sha256:" + "2" * 64, verified_operation_count=1, postimage_verified=True, source_state_matches_approved_patch=True, main_branch_integration_authorized=False, digest="")
    item = SelfDevelopmentPostPromotionVerificationSnapshot(**{**base, **changes})
    item = replace(item, verification_id="sdpv_" + _canonical(_snapshot_payload(item, include_id=False))[7:31])
    return replace(item, digest=_canonical(_snapshot_payload(item)))


def test_verification_store_is_durable_and_idempotent(tmp_path: Path):
    item = snapshot(); store = SelfDevelopmentPostPromotionVerificationStore(root=tmp_path)
    assert store.append(item) == item
    fresh = SelfDevelopmentPostPromotionVerificationStore(root=tmp_path)
    assert fresh.get_by_execution(execution_id=item.execution_id, execution_digest=item.execution_digest) == item
    assert fresh.append(item) == item


def test_corrupted_store_fails_closed(tmp_path: Path):
    item = snapshot(); store = SelfDevelopmentPostPromotionVerificationStore(root=tmp_path); store.append(item)
    path = next((tmp_path / "post_promotion_verifications").glob("*.json")); data = json.loads(path.read_text(encoding="utf-8")); data["postimage_verified"] = False; path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SelfDevelopmentPostPromotionVerificationIntegrityError):
        store.get_by_execution(execution_id=item.execution_id, execution_digest=item.execution_digest)
