"""Durable replay evidence for supervised promotion execution."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

SELF_DEVELOPMENT_PROMOTION_RECEIPT_REVISION = "self-development-promotion-execution-receipt-v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

class SelfDevelopmentPromotionReceiptError(ValueError): pass
class SelfDevelopmentPromotionReceiptValidationError(SelfDevelopmentPromotionReceiptError): pass
class SelfDevelopmentPromotionReceiptIntegrityError(SelfDevelopmentPromotionReceiptError): pass
class SelfDevelopmentPromotionReceiptConflictError(SelfDevelopmentPromotionReceiptError): pass

def _canonical(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()

@dataclass(frozen=True)
class SelfDevelopmentPromotionExecutionReceipt:
    revision: str
    receipt_id: str
    workspace_path: str
    project_key: str
    binding_id: str
    binding_digest: str
    authority_id: str
    authority_digest: str
    candidate_id: str
    candidate_digest: str
    plan_digest: str
    preview_digest: str
    patch_approval_digest: str
    safe_patch_execution_receipt_id: str
    safe_patch_execution_receipt_digest: str
    promotion_executed: bool
    source_mutation_performed: bool
    main_branch_mutation_performed: bool
    digest: str
    # SafePatchPlanSnapshot exposes only a digest; no upstream plan ID exists.
    plan_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"revision": self.revision, "receipt_id": self.receipt_id, "workspace_path": self.workspace_path, "project_key": self.project_key, "binding_id": self.binding_id, "binding_digest": self.binding_digest, "authority_id": self.authority_id, "authority_digest": self.authority_digest, "candidate_id": self.candidate_id, "candidate_digest": self.candidate_digest, "plan_id": self.plan_id, "plan_digest": self.plan_digest, "preview_digest": self.preview_digest, "patch_approval_digest": self.patch_approval_digest, "safe_patch_execution_receipt_id": self.safe_patch_execution_receipt_id, "safe_patch_execution_receipt_digest": self.safe_patch_execution_receipt_digest, "promotion_executed": self.promotion_executed, "source_mutation_performed": self.source_mutation_performed, "main_branch_mutation_performed": self.main_branch_mutation_performed, "digest": self.digest}

def _payload(receipt: SelfDevelopmentPromotionExecutionReceipt, *, include_id: bool = True) -> dict[str, object]:
    payload = receipt.to_dict(); payload.pop("digest", None)
    if not include_id: payload.pop("receipt_id", None)
    return payload

def _validate_receipt(receipt: SelfDevelopmentPromotionExecutionReceipt) -> None:
    if not isinstance(receipt, SelfDevelopmentPromotionExecutionReceipt): raise SelfDevelopmentPromotionReceiptValidationError("Promotion receipt type is invalid.")
    if receipt.revision != SELF_DEVELOPMENT_PROMOTION_RECEIPT_REVISION: raise SelfDevelopmentPromotionReceiptIntegrityError("Promotion receipt revision is invalid.")
    digests = (receipt.binding_digest, receipt.authority_digest, receipt.candidate_digest, receipt.plan_digest, receipt.preview_digest, receipt.patch_approval_digest, receipt.safe_patch_execution_receipt_digest, receipt.digest)
    if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in digests): raise SelfDevelopmentPromotionReceiptIntegrityError("Promotion receipt digest is invalid.")
    if not isinstance(receipt.receipt_id, str) or re.fullmatch(r"sdpr_[0-9a-f]{24}", receipt.receipt_id) is None: raise SelfDevelopmentPromotionReceiptIntegrityError("Promotion receipt identity is invalid.")
    if not receipt.binding_id or not receipt.authority_id or not receipt.candidate_id or not receipt.project_key or not receipt.workspace_path: raise SelfDevelopmentPromotionReceiptValidationError("Promotion receipt identity fields are invalid.")
    if receipt.plan_id is not None and (not isinstance(receipt.plan_id, str) or not receipt.plan_id): raise SelfDevelopmentPromotionReceiptValidationError("Promotion receipt plan identity is invalid.")
    if not receipt.promotion_executed or not receipt.source_mutation_performed or receipt.main_branch_mutation_performed: raise SelfDevelopmentPromotionReceiptIntegrityError("Promotion receipt success invariants are invalid.")
    if receipt.receipt_id != "sdpr_" + _canonical(_payload(receipt, include_id=False))[7:31]: raise SelfDevelopmentPromotionReceiptIntegrityError("Promotion receipt identity does not match its content.")
    if _canonical(_payload(receipt)) != receipt.digest: raise SelfDevelopmentPromotionReceiptIntegrityError("Promotion receipt digest does not match its content.")

class SelfDevelopmentPromotionReceiptStore:
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.receipts_dir = self.root / "promotion_execution_receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(binding_id: str, binding_digest: str) -> str:
        return hashlib.sha256((binding_id + "\0" + binding_digest).encode("utf-8")).hexdigest()

    def _path(self, binding_id: str, binding_digest: str) -> Path:
        return self.receipts_dir / (self._key(binding_id, binding_digest) + ".json")

    def _load_path(self, path: Path) -> SelfDevelopmentPromotionExecutionReceipt | None:
        if not path.exists(): return None
        try:
            receipt = SelfDevelopmentPromotionExecutionReceipt(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise SelfDevelopmentPromotionReceiptIntegrityError("Persisted promotion receipt is malformed.") from exc
        _validate_receipt(receipt)
        return receipt

    def append(self, receipt: SelfDevelopmentPromotionExecutionReceipt) -> SelfDevelopmentPromotionExecutionReceipt:
        _validate_receipt(receipt)
        path = self._path(receipt.binding_id, receipt.binding_digest)
        if path.exists():
            self._load_path(path)
            raise SelfDevelopmentPromotionReceiptConflictError("Promotion binding has already been consumed.")
        data = json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        try:
            with path.open("xb") as handle:
                handle.write(data); handle.flush()
        except FileExistsError as exc:
            raise SelfDevelopmentPromotionReceiptConflictError("Promotion binding has already been consumed.") from exc
        except OSError as exc:
            raise SelfDevelopmentPromotionReceiptError("Promotion receipt persistence failed.") from exc
        return receipt

    def get_by_binding(self, *, binding_id: str, binding_digest: str) -> SelfDevelopmentPromotionExecutionReceipt | None:
        if not isinstance(binding_id, str) or not binding_id or not isinstance(binding_digest, str) or not _SHA256.fullmatch(binding_digest): raise SelfDevelopmentPromotionReceiptValidationError("Promotion binding lookup is invalid.")
        return self._load_path(self._path(binding_id, binding_digest))

    def is_consumed(self, *, binding_id: str, binding_digest: str) -> bool:
        return self.get_by_binding(binding_id=binding_id, binding_digest=binding_digest) is not None
