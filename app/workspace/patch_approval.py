from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import ToolError
from app.workspace.patch_plan import PatchChangeRequest, SafePatchPlan, SafePatchPlanError, SafePatchPlanStaleError, SafePatchOperationSnapshot
from app.workspace.policy import WorkspacePolicy

SAFE_PATCH_PREVIEW_REVISION = "safe-patch-preview-v1"
SAFE_PATCH_APPROVAL_BINDING_REVISION = "safe-patch-approval-binding-v1"


class SafePatchApprovalError(ValueError): pass
class SafePatchApprovalStaleError(SafePatchApprovalError): pass
class SafePatchApprovalMismatch(SafePatchApprovalError): pass


def _hash(data: bytes) -> str: return "sha256:" + hashlib.sha256(data).hexdigest()
def _digest(payload: dict) -> str: return _hash(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class SafePatchPreviewOperation:
    path: str; operation: str; preimage_state: str; preimage_sha256: str | None; preimage_size_bytes: int | None; replacement_sha256: str | None; replacement_size_bytes: int | None; added_lines: int; removed_lines: int; diff: str
    def to_dict(self):
        return {"path":self.path,"operation":self.operation,"preimage_state":self.preimage_state,"preimage_sha256":self.preimage_sha256,"preimage_size_bytes":self.preimage_size_bytes,"replacement_sha256":self.replacement_sha256,"replacement_size_bytes":self.replacement_size_bytes,"added_lines":self.added_lines,"removed_lines":self.removed_lines,"diff":self.diff}


@dataclass(frozen=True)
class SafePatchPreviewSnapshot:
    revision: str; workspace_path: str; project_key: str; repository_map_digest: str; scope_lock_digest: str; plan_digest: str; operations: tuple[SafePatchPreviewOperation, ...]; operation_count: int; total_added_lines: int; total_removed_lines: int; total_diff_chars: int; digest: str
    def to_dict(self):
        return {"revision":self.revision,"workspace_path":self.workspace_path,"project_key":self.project_key,"repository_map_digest":self.repository_map_digest,"scope_lock_digest":self.scope_lock_digest,"plan_digest":self.plan_digest,"operations":[o.to_dict() for o in self.operations],"operation_count":self.operation_count,"total_added_lines":self.total_added_lines,"total_removed_lines":self.total_removed_lines,"total_diff_chars":self.total_diff_chars,"digest":self.digest}


@dataclass(frozen=True)
class SafePatchApprovalBindingSnapshot:
    revision: str; workspace_path: str; project_key: str; repository_map_digest: str; scope_lock_digest: str; plan_digest: str; preview_digest: str; operations: tuple[SafePatchOperationSnapshot, ...]; operation_count: int; digest: str
    def to_dict(self):
        return {"revision":self.revision,"workspace_path":self.workspace_path,"project_key":self.project_key,"repository_map_digest":self.repository_map_digest,"scope_lock_digest":self.scope_lock_digest,"plan_digest":self.plan_digest,"preview_digest":self.preview_digest,"operations":[o.to_dict() for o in self.operations],"operation_count":self.operation_count,"digest":self.digest}


@dataclass(frozen=True)
class PreparedSafePatchApproval:
    preview: SafePatchPreviewSnapshot
    binding: SafePatchApprovalBindingSnapshot


class SafePatchApprovalBuilder:
    def __init__(self, *, project_root: Path, workspace_path: str, project_key: str, max_file_bytes: int = 1_048_576, max_search_results: int = 1_000, max_operation_diff_chars: int = 20_000, max_total_diff_chars: int = 60_000):
        root=Path(project_root).expanduser()
        if not root.exists() or not root.is_dir() or root.is_symlink() or not workspace_path or not project_key or max_file_bytes<=0 or not 1<=max_operation_diff_chars<=200_000 or not max_operation_diff_chars<=max_total_diff_chars<=1_000_000: raise SafePatchApprovalError("Safe patch approval construction is invalid.")
        self.project_root=root.resolve(); self.workspace_path=workspace_path; self.project_key=project_key; self.max_file_bytes=max_file_bytes; self.max_operation_diff_chars=max_operation_diff_chars; self.max_total_diff_chars=max_total_diff_chars
        self.policy=WorkspacePolicy(root=self.project_root,max_file_bytes=max_file_bytes,max_search_results=max_search_results)

    @classmethod
    def from_runtime(cls,runtime,*,settings,max_operation_diff_chars=20_000,max_total_diff_chars=60_000):
        return cls(project_root=runtime.project_root,workspace_path=runtime.workspace_path,project_key=runtime.project_key,max_file_bytes=settings.workspace_max_file_bytes,max_search_results=settings.workspace_max_search_results,max_operation_diff_chars=max_operation_diff_chars,max_total_diff_chars=max_total_diff_chars)

    def _validate_plan(self, plan):
        try:
            snapshot = plan.snapshot
            if snapshot.revision!="safe-patch-plan-v1" or snapshot.operation_count!=len(snapshot.operations) or [o.path for o in snapshot.operations]!=sorted(o.path for o in snapshot.operations) or len({o.path for o in snapshot.operations}) != snapshot.operation_count: raise ValueError
            if (snapshot.workspace_path, snapshot.project_key) != (self.workspace_path, self.project_key): raise ValueError
            if not _SHA256.fullmatch(snapshot.repository_map_digest) or not _SHA256.fullmatch(snapshot.scope_lock_digest) or not _SHA256.fullmatch(snapshot.digest): raise ValueError
            for operation in snapshot.operations:
                if not operation.path or operation.operation not in {"create", "replace", "delete"}: raise ValueError
                if operation.preimage_sha256 is not None and not _SHA256.fullmatch(operation.preimage_sha256): raise ValueError
                if operation.replacement_sha256 is not None and not _SHA256.fullmatch(operation.replacement_sha256): raise ValueError
            payload=plan.snapshot.to_dict(); digest=payload.pop("digest")
            if _digest(payload)!=digest: raise ValueError
            if getattr(plan,"_project_root",None).resolve()!=self.project_root: raise ValueError
        except Exception: raise SafePatchApprovalError("Safe patch approval plan does not match the bound project.") from None

    def _prepare_once(self, plan, changes):
        self._validate_plan(plan); payload=list(changes)
        if len(payload)!=plan.snapshot.operation_count: raise SafePatchApprovalMismatch("Patch approval payload does not exactly match the plan.")
        canonical={}
        try:
            for change in payload:
                op=plan.assert_change(path=change.path,operation=change.operation,replacement_text=change.replacement_text)
                if op.path in canonical: raise ValueError
                canonical[op.path]=change
        except Exception: raise SafePatchApprovalMismatch("Patch approval payload does not exactly match the plan.") from None
        if set(canonical)!={o.path for o in plan.snapshot.operations}: raise SafePatchApprovalMismatch("Patch approval payload does not exactly match the plan.")
        try: plan.assert_current()
        except SafePatchPlanStaleError: raise SafePatchApprovalStaleError("Patch approval pre-image is stale.") from None
        previews=[]
        for operation in plan.snapshot.operations:
            change=canonical[operation.path]
            try:
                target=self.policy.resolve(operation.path,must_exist=False)
            except (ToolError, OSError, ValueError):
                raise SafePatchApprovalMismatch("Patch approval payload does not exactly match the plan.") from None
            if operation.operation=="create": old=""; old_bytes=b""
            else:
                try: old_bytes=target.read_bytes()
                except OSError: raise SafePatchApprovalStaleError("Patch approval pre-image is stale.") from None
                if len(old_bytes)>self.max_file_bytes or target.is_symlink() or not target.is_file(): raise SafePatchApprovalStaleError("Patch approval pre-image is stale.")
                if _hash(old_bytes)!=operation.preimage_sha256 or len(old_bytes)!=operation.preimage_size_bytes: raise SafePatchApprovalStaleError("Patch approval pre-image is stale.")
                try: old=old_bytes.decode("utf-8")
                except UnicodeDecodeError: raise SafePatchApprovalError("Safe patch preview requires UTF-8 text targets.") from None
                if "\x00" in old: raise SafePatchApprovalError("Safe patch preview requires UTF-8 text targets.")
            new="" if operation.operation=="delete" else change.replacement_text
            diff="\n".join(difflib.unified_diff(old.splitlines(),new.splitlines(),fromfile="a/"+operation.path,tofile="b/"+operation.path,lineterm=""))
            if len(diff)>self.max_operation_diff_chars: raise SafePatchApprovalError("Safe patch preview exceeds the per-operation display limit.")
            added=sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")); removed=sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
            previews.append(SafePatchPreviewOperation(operation.path,operation.operation,operation.preimage_state,operation.preimage_sha256,operation.preimage_size_bytes,operation.replacement_sha256,operation.replacement_size_bytes,added,removed,diff))
        try: plan.assert_current()
        except SafePatchPlanStaleError: raise SafePatchApprovalStaleError("Patch approval pre-image is stale.") from None
        total_added=sum(p.added_lines for p in previews); total_removed=sum(p.removed_lines for p in previews); total_chars=sum(len(p.diff) for p in previews)
        if total_chars>self.max_total_diff_chars: raise SafePatchApprovalError("Safe patch preview exceeds the total display limit.")
        p_payload={"revision":SAFE_PATCH_PREVIEW_REVISION,"workspace_path":self.workspace_path,"project_key":self.project_key,"repository_map_digest":plan.snapshot.repository_map_digest,"scope_lock_digest":plan.snapshot.scope_lock_digest,"plan_digest":plan.snapshot.digest,"operations":[p.to_dict() for p in previews],"operation_count":len(previews),"total_added_lines":total_added,"total_removed_lines":total_removed,"total_diff_chars":total_chars}
        preview=SafePatchPreviewSnapshot(SAFE_PATCH_PREVIEW_REVISION,self.workspace_path,self.project_key,plan.snapshot.repository_map_digest,plan.snapshot.scope_lock_digest,plan.snapshot.digest,tuple(previews),len(previews),total_added,total_removed,total_chars,_digest(p_payload))
        b_payload={"revision":SAFE_PATCH_APPROVAL_BINDING_REVISION,"workspace_path":self.workspace_path,"project_key":self.project_key,"repository_map_digest":plan.snapshot.repository_map_digest,"scope_lock_digest":plan.snapshot.scope_lock_digest,"plan_digest":plan.snapshot.digest,"preview_digest":preview.digest,"operations":[o.to_dict() for o in plan.snapshot.operations],"operation_count":len(plan.snapshot.operations)}
        binding=SafePatchApprovalBindingSnapshot(SAFE_PATCH_APPROVAL_BINDING_REVISION,self.workspace_path,self.project_key,plan.snapshot.repository_map_digest,plan.snapshot.scope_lock_digest,plan.snapshot.digest,preview.digest,tuple(plan.snapshot.operations),len(plan.snapshot.operations),_digest(b_payload))
        return PreparedSafePatchApproval(preview,binding)

    def prepare(self, *, plan: SafePatchPlan, changes): return self._prepare_once(plan,changes)

    def assert_binding(self, *, plan, changes, preview, binding):
        self._verify_supplied_preview(preview)
        self._verify_supplied_binding(binding)
        self._validate_plan(plan)
        if (preview.workspace_path, preview.project_key) != (self.workspace_path, self.project_key) or (binding.workspace_path, binding.project_key) != (self.workspace_path, self.project_key):
            raise SafePatchApprovalMismatch("Safe patch approval binding does not match the bound project.")
        snapshot = plan.snapshot
        if (preview.repository_map_digest, preview.scope_lock_digest, preview.plan_digest) != (snapshot.repository_map_digest, snapshot.scope_lock_digest, snapshot.digest) or (binding.repository_map_digest, binding.scope_lock_digest, binding.plan_digest) != (snapshot.repository_map_digest, snapshot.scope_lock_digest, snapshot.digest):
            raise SafePatchApprovalMismatch("Safe patch approval binding does not match the current plan.")
        if binding.preview_digest != preview.digest or binding.operations != snapshot.operations:
            raise SafePatchApprovalMismatch("Safe patch approval binding does not match the preview.")
        current=self._prepare_once(plan,changes)
        if preview.digest!=current.preview.digest or binding.digest!=current.binding.digest: raise SafePatchApprovalMismatch("Safe patch approval binding does not match the current plan.")

    @staticmethod
    def _verify_supplied_preview(preview):
        try:
            if preview.revision != SAFE_PATCH_PREVIEW_REVISION or preview.operation_count != len(preview.operations): raise ValueError
            if [item.path for item in preview.operations] != sorted(item.path for item in preview.operations) or len({item.path for item in preview.operations}) != preview.operation_count: raise ValueError
            if preview.total_added_lines != sum(item.added_lines for item in preview.operations) or preview.total_removed_lines != sum(item.removed_lines for item in preview.operations) or preview.total_diff_chars != sum(len(item.diff) for item in preview.operations): raise ValueError
            if not _SHA256.fullmatch(preview.digest) or not _SHA256.fullmatch(preview.repository_map_digest) or not _SHA256.fullmatch(preview.scope_lock_digest) or not _SHA256.fullmatch(preview.plan_digest): raise ValueError
            for item in preview.operations:
                if not item.path or item.operation not in {"create", "replace", "delete"} or item.preimage_state not in {"absent", "file"} or item.added_lines < 0 or item.removed_lines < 0 or (item.preimage_size_bytes is not None and item.preimage_size_bytes < 0) or (item.replacement_size_bytes is not None and item.replacement_size_bytes < 0) or item.preimage_sha256 is not None and not _SHA256.fullmatch(item.preimage_sha256) or item.replacement_sha256 is not None and not _SHA256.fullmatch(item.replacement_sha256): raise ValueError
            payload = preview.to_dict(); digest = payload.pop("digest")
            if _digest(payload) != digest: raise ValueError
        except Exception:
            raise SafePatchApprovalMismatch("Safe patch approval preview is invalid.") from None

    @staticmethod
    def _verify_supplied_binding(binding):
        try:
            if binding.revision != SAFE_PATCH_APPROVAL_BINDING_REVISION or binding.operation_count != len(binding.operations): raise ValueError
            if [item.path for item in binding.operations] != sorted(item.path for item in binding.operations) or len({item.path for item in binding.operations}) != binding.operation_count: raise ValueError
            if not _SHA256.fullmatch(binding.digest) or not _SHA256.fullmatch(binding.repository_map_digest) or not _SHA256.fullmatch(binding.scope_lock_digest) or not _SHA256.fullmatch(binding.plan_digest) or not _SHA256.fullmatch(binding.preview_digest): raise ValueError
            for item in binding.operations:
                if not item.path or item.operation not in {"create", "replace", "delete"} or item.preimage_state not in {"absent", "file"} or (item.preimage_size_bytes is not None and item.preimage_size_bytes < 0) or (item.replacement_size_bytes is not None and item.replacement_size_bytes < 0) or item.preimage_sha256 is not None and not _SHA256.fullmatch(item.preimage_sha256) or item.replacement_sha256 is not None and not _SHA256.fullmatch(item.replacement_sha256): raise ValueError
            payload = binding.to_dict(); digest = payload.pop("digest")
            if _digest(payload) != digest: raise ValueError
        except Exception:
            raise SafePatchApprovalMismatch("Safe patch approval binding is invalid.") from None
