from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.improvement.promotion_execution import (
    SELF_DEVELOPMENT_PROMOTION_EXECUTION_CLAIM_REVISION,
    SelfDevelopmentPromotionExecutionClaim,
    SelfDevelopmentPromotionExecutionClaimStore,
    SelfDevelopmentPromotionExecutionIntegrityError,
    SelfDevelopmentPromotionExecutionRecoveryRequiredError,
    _claim_payload,
    _digest,
)


def claim(**changes):
    base = dict(
        revision=SELF_DEVELOPMENT_PROMOTION_EXECUTION_CLAIM_REVISION,
        claim_id="",
        workspace_path="workspace",
        project_key="project",
        authority_id="sda_" + "a" * 24,
        authority_digest="sha256:" + "b" * 64,
        binding_id="sdpb_" + "c" * 24,
        binding_digest="sha256:" + "d" * 64,
        candidate_id="sdc_" + "e" * 24,
        candidate_digest="sha256:" + "f" * 64,
        plan_digest="sha256:" + "1" * 64,
        preview_digest="sha256:" + "2" * 64,
        patch_approval_digest="sha256:" + "3" * 64,
        change_payload_digest="sha256:" + "4" * 64,
        digest="",
    )
    item = SelfDevelopmentPromotionExecutionClaim(**{**base, **changes})
    item = replace(item, claim_id="sdpc_" + _digest(_claim_payload(item, include_id=False))[7:31])
    return replace(item, digest=_digest(_claim_payload(item)))


def test_claim_is_deterministic_and_survives_restart(tmp_path: Path):
    item = claim()
    assert item == claim()
    first = SelfDevelopmentPromotionExecutionClaimStore(root=tmp_path)
    assert first.claim(item) == item
    second = SelfDevelopmentPromotionExecutionClaimStore(root=tmp_path)
    assert second.get_by_binding(binding_id=item.binding_id, binding_digest=item.binding_digest) == item
    assert second.is_claimed(binding_id=item.binding_id, binding_digest=item.binding_digest)
    with pytest.raises(SelfDevelopmentPromotionExecutionRecoveryRequiredError):
        second.claim(item)


def test_corrupt_claim_fails_closed(tmp_path: Path):
    item = claim()
    store = SelfDevelopmentPromotionExecutionClaimStore(root=tmp_path)
    store.claim(item)
    path = next((tmp_path / "promotion_execution_claims").glob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["change_payload_digest"] = "sha256:" + "9" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SelfDevelopmentPromotionExecutionIntegrityError):
        store.is_claimed(binding_id=item.binding_id, binding_digest=item.binding_digest)
