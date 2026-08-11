from dataclasses import replace
import json
from pathlib import Path
import pytest
from app.improvement.promotion_receipts import SelfDevelopmentPromotionExecutionReceipt, SelfDevelopmentPromotionReceiptConflictError, SelfDevelopmentPromotionReceiptIntegrityError, SelfDevelopmentPromotionReceiptStore, _canonical, _payload

def receipt(**changes):
    base = dict(revision="self-development-promotion-execution-receipt-v1", receipt_id="", workspace_path="ws", project_key="project-a", binding_id="sdpb_" + "a" * 24, binding_digest="sha256:" + "b" * 64, authority_id="sda_" + "c" * 24, authority_digest="sha256:" + "d" * 64, candidate_id="sdc_" + "e" * 24, candidate_digest="sha256:" + "f" * 64, plan_digest="sha256:" + "1" * 64, preview_digest="sha256:" + "2" * 64, patch_approval_digest="sha256:" + "3" * 64, safe_patch_execution_receipt_id="receipt-1", safe_patch_execution_receipt_digest="sha256:" + "4" * 64, promotion_executed=True, source_mutation_performed=True, main_branch_mutation_performed=False, digest="")
    item = SelfDevelopmentPromotionExecutionReceipt(**{**base, **changes})
    item = replace(item, receipt_id="sdpr_" + _canonical(_payload(item, include_id=False))[7:31])
    return replace(item, digest=_canonical(_payload(item)))

def test_append_reload_and_duplicate_conflict(tmp_path: Path):
    store = SelfDevelopmentPromotionReceiptStore(root=tmp_path); item = receipt(); assert store.append(item) == item
    reloaded = SelfDevelopmentPromotionReceiptStore(root=tmp_path)
    assert reloaded.is_consumed(binding_id=item.binding_id, binding_digest=item.binding_digest)
    assert reloaded.get_by_binding(binding_id=item.binding_id, binding_digest=item.binding_digest) == item
    with pytest.raises(SelfDevelopmentPromotionReceiptConflictError): reloaded.append(item)

def test_corruption_fails_closed(tmp_path: Path):
    store = SelfDevelopmentPromotionReceiptStore(root=tmp_path); item = receipt(); store.append(item)
    path = next((tmp_path / "promotion_execution_receipts").glob("*.json")); data = json.loads(path.read_text(encoding="utf-8")); data["promotion_executed"] = False; path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SelfDevelopmentPromotionReceiptIntegrityError): store.is_consumed(binding_id=item.binding_id, binding_digest=item.binding_digest)

def test_different_binding_is_independent(tmp_path: Path):
    store = SelfDevelopmentPromotionReceiptStore(root=tmp_path); first = receipt(); second = receipt(binding_id="sdpb_" + "9" * 24)
    assert store.append(first) == first and store.append(second) == second

def test_same_semantics_have_deterministic_identity_and_serialization():
    first, second = receipt(), receipt()
    assert first.receipt_id == second.receipt_id
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()

def test_changed_execution_result_cannot_reconsume_binding(tmp_path: Path):
    store = SelfDevelopmentPromotionReceiptStore(root=tmp_path); first = receipt(); store.append(first)
    changed = receipt(safe_patch_execution_receipt_id="receipt-2")
    with pytest.raises(SelfDevelopmentPromotionReceiptConflictError): store.append(changed)

def test_wrong_binding_digest_is_exact_lookup(tmp_path: Path):
    store = SelfDevelopmentPromotionReceiptStore(root=tmp_path); item = receipt(); store.append(item)
    assert store.get_by_binding(binding_id=item.binding_id, binding_digest="sha256:" + "9" * 64) is None
    assert not store.is_consumed(binding_id=item.binding_id, binding_digest="sha256:" + "9" * 64)

def test_unsafe_success_flags_are_rejected(tmp_path: Path):
    with pytest.raises(SelfDevelopmentPromotionReceiptIntegrityError):
        item = receipt(promotion_executed=False)
        SelfDevelopmentPromotionReceiptStore(root=tmp_path).append(item)
