"""Supervised local-only Git integration for an already verified workspace."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, re, subprocess
from pathlib import Path
from typing import Any

from app.improvement.git_integration_approval import SelfDevelopmentGitIntegrationApprovalSnapshot
from app.improvement.post_promotion_verification import SelfDevelopmentPostPromotionVerificationSnapshot
from app.workspace.patch_plan import SafePatchPlan
from app.workspace.policy import WorkspacePolicy

CLAIM_REVISION = "self-development-local-git-integration-claim-v1"
RECEIPT_REVISION = "self-development-local-git-integration-receipt-v1"
INTEGRATION_REVISION = "self-development-local-git-integration-v1"
_SHA = re.compile(r"^[0-9a-f]{40}$"); _DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

class SelfDevelopmentGitIntegrationError(RuntimeError): pass
class SelfDevelopmentGitIntegrationValidationError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationIntegrityError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationAuthorizationError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationProjectError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationConflictError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationReplayError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationRecoveryRequiredError(SelfDevelopmentGitIntegrationError): pass
class SelfDevelopmentGitIntegrationGitError(SelfDevelopmentGitIntegrationError): pass

def _canon(value: object) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode(); return "sha256:"+hashlib.sha256(raw).hexdigest()

def _payload(obj: Any, *, include_id=True):
    d=obj.to_dict(); d.pop("digest",None)
    if not include_id: d.pop("claim_id",None); d.pop("receipt_id",None); d.pop("integration_id",None)
    return d

@dataclass(frozen=True)
class SelfDevelopmentGitIntegrationClaim:
    revision:str; claim_id:str; project_key:str; workspace_path:str; approval_id:str; approval_digest:str; verification_id:str; verification_digest:str; execution_id:str; execution_digest:str; source_branch:str; target_branch:str; expected_main_sha:str; approved_change_set_digest:str; digest:str
    def to_dict(self): return {n:getattr(self,n) for n in self.__dataclass_fields__}

@dataclass(frozen=True)
class SelfDevelopmentGitIntegrationReceipt:
    revision:str; receipt_id:str; project_key:str; workspace_path:str; approval_id:str; approval_digest:str; verification_id:str; verification_digest:str; execution_id:str; execution_digest:str; source_branch:str; target_branch:str; previous_main_sha:str; promotion_commit_sha:str; resulting_main_sha:str; approved_change_set_digest:str; local_integration_completed:bool; remote_publication_performed:bool; digest:str
    def to_dict(self): return {n:getattr(self,n) for n in self.__dataclass_fields__}

@dataclass(frozen=True)
class SelfDevelopmentGitIntegrationSnapshot:
    revision:str; integration_id:str; project_key:str; workspace_path:str; approval_id:str; approval_digest:str; verification_id:str; verification_digest:str; source_branch:str; target_branch:str; previous_main_sha:str; promotion_commit_sha:str; resulting_main_sha:str; approved_change_set_digest:str; claim_id:str; claim_digest:str; receipt_id:str; receipt_digest:str; local_integration_completed:bool; remote_publication_performed:bool; digest:str
    def to_dict(self): return {n:getattr(self,n) for n in self.__dataclass_fields__}

class SelfDevelopmentGitIntegrationStore:
    def __init__(self, *, root:Path): self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
    def _path(self, kind, key): return self.root/f"{kind}-{hashlib.sha256(key.encode()).hexdigest()}.json"
    def _load(self,path,cls):
        if not path.exists(): return None
        try: obj=cls(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as e: raise SelfDevelopmentGitIntegrationIntegrityError("Persisted integration evidence is malformed.") from e
        data=obj.to_dict(); digest=data.pop("digest")
        if _canon(data)!=digest: raise SelfDevelopmentGitIntegrationIntegrityError("Persisted integration evidence is corrupt.")
        return obj
    def _put(self,path,obj):
        data=json.dumps(obj.to_dict(),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        try:
            with path.open("xb") as f: f.write(data); f.flush()
        except FileExistsError as e: raise SelfDevelopmentGitIntegrationConflictError("Integration evidence already exists.") from e
    def get_claim_by_approval(self, approval_id, approval_digest): return self._load(self._path("claim",approval_id+"\0"+approval_digest),SelfDevelopmentGitIntegrationClaim)
    def get_receipt_by_approval(self, approval_id, approval_digest): return self._load(self._path("receipt",approval_id+"\0"+approval_digest),SelfDevelopmentGitIntegrationReceipt)
    def append_claim(self,c): self._put(self._path("claim",c.approval_id+"\0"+c.approval_digest),c); return c
    def append_receipt(self,r): self._put(self._path("receipt",r.approval_id+"\0"+r.approval_digest),r); return r

class SelfDevelopmentGitIntegrator:
    def __init__(self, *, project_key:str, integration_store:SelfDevelopmentGitIntegrationStore, integration_worktree_root:Path):
        self.project_key=project_key; self.store=integration_store; self.worktree_root=Path(integration_worktree_root).resolve()
    def _git(self, root:Path, *args, write=False):
        forbidden={"push","fetch","pull","clone","ls-remote","reset","clean","restore","rebase","cherry-pick","update-ref"}
        if any(a in forbidden or a in {"--force","--amend"} for a in args): raise SelfDevelopmentGitIntegrationGitError("Forbidden Git operation.")
        try: out=subprocess.run(["git",*args],cwd=str(root),shell=False,capture_output=True,text=True,check=False,timeout=30)
        except Exception as e: raise SelfDevelopmentGitIntegrationGitError("Git invocation failed.") from e
        if out.returncode: raise SelfDevelopmentGitIntegrationGitError(out.stderr.strip() or "Git operation failed.")
        return out.stdout
    def integrate(self, *, verification:SelfDevelopmentPostPromotionVerificationSnapshot, approval:SelfDevelopmentGitIntegrationApprovalSnapshot, plan:SafePatchPlan):
        if not isinstance(verification,SelfDevelopmentPostPromotionVerificationSnapshot) or not isinstance(approval,SelfDevelopmentGitIntegrationApprovalSnapshot): raise SelfDevelopmentGitIntegrationValidationError("Canonical inputs are invalid.")
        vd=verification.to_dict(); vdig=vd.pop("digest")
        if _canon(vd)!=vdig or not verification.postimage_verified or not verification.source_state_matches_approved_patch or verification.main_branch_integration_authorized: raise SelfDevelopmentGitIntegrationIntegrityError("Verification is invalid.")
        ad=approval.to_dict(); adig=ad.pop("digest")
        if _canon(ad)!=adig or approval.decision!="approve" or not approval.local_git_integration_authorized or approval.remote_publication_authorized: raise SelfDevelopmentGitIntegrationAuthorizationError("Git integration approval is invalid.")
        if approval.verification_id!=verification.verification_id or approval.verification_digest!=verification.digest or approval.project_key!=self.project_key or approval.workspace_path!=verification.workspace_path or approval.target_branch!="main" or approval.execution_id!=verification.execution_id or approval.execution_digest!=verification.execution_digest: raise SelfDevelopmentGitIntegrationAuthorizationError("Approval and verification do not match.")
        validator=WorkspacePolicy(root=plan._project_root,max_file_bytes=1_048_576,max_search_results=1000)
        try:
            from app.workspace.patch_approval import SafePatchApprovalBuilder; SafePatchApprovalBuilder(project_root=plan._project_root,workspace_path=verification.workspace_path,project_key=self.project_key)._validate_plan(plan)
        except Exception as e: raise SelfDevelopmentGitIntegrationIntegrityError("Plan is invalid.") from e
        if plan.snapshot.digest!=verification.plan_digest: raise SelfDevelopmentGitIntegrationAuthorizationError("Plan does not match verification.")
        root=Path(plan._project_root).resolve(); branch=self._git(root,"branch","--show-current").strip(); head=self._git(root,"rev-parse","HEAD").strip(); main=self._git(root,"rev-parse","main").strip()
        if branch!=approval.source_branch or branch=="main" or head!=approval.expected_main_sha or main!=approval.expected_main_sha: raise SelfDevelopmentGitIntegrationConflictError("Git baseline changed.")
        if self._git(root,"diff","--cached","--name-only").strip(): raise SelfDevelopmentGitIntegrationConflictError("Pre-staged changes exist.")
        expected=sorted(op.path for op in plan.snapshot.operations); status=self._git(root,"status","--porcelain=v1"); actual=sorted(line[3:].strip() for line in status.splitlines() if line)
        if actual!=expected: raise SelfDevelopmentGitIntegrationAuthorizationError("Git-visible paths do not match the approved plan.")
        for op in plan.snapshot.operations:
            p=validator.resolve(op.path,must_exist=False)
            if op.operation=="delete":
                if p.exists(): raise SelfDevelopmentGitIntegrationAuthorizationError("Postimage mismatch.")
            else:
                if not p.is_file() or p.is_symlink(): raise SelfDevelopmentGitIntegrationAuthorizationError("Postimage mismatch.")
                b=p.read_bytes()
                if "sha256:"+hashlib.sha256(b).hexdigest()!=op.replacement_sha256 or len(b)!=op.replacement_size_bytes: raise SelfDevelopmentGitIntegrationAuthorizationError("Postimage mismatch.")
        change_digest=_canon([op.to_dict() for op in plan.snapshot.operations]); key_payload={"revision":CLAIM_REVISION,"approval_id":approval.approval_id,"approval_digest":approval.digest,"verification_id":verification.verification_id,"verification_digest":verification.digest,"execution_id":verification.execution_id,"execution_digest":verification.execution_digest,"source_branch":branch,"target_branch":"main","expected_main_sha":approval.expected_main_sha,"approved_change_set_digest":change_digest}; claim_id="sdgic_"+_canon(key_payload)[7:31]
        if self.store.get_receipt_by_approval(approval.approval_id,approval.digest): raise SelfDevelopmentGitIntegrationReplayError("Integration already completed.")
        if self.store.get_claim_by_approval(approval.approval_id,approval.digest): raise SelfDevelopmentGitIntegrationRecoveryRequiredError("Integration recovery is required.")
        claim=SelfDevelopmentGitIntegrationClaim(CLAIM_REVISION,claim_id,self.project_key,verification.workspace_path,approval.approval_id,approval.digest,verification.verification_id,verification.digest,verification.execution_id,verification.execution_digest,branch,"main",approval.expected_main_sha,change_digest,""); claim_data=claim.to_dict(); claim_data.pop("digest"); claim=SelfDevelopmentGitIntegrationClaim(**{**claim.to_dict(),"digest":_canon(claim_data)}); self.store.append_claim(claim)
        self._git(root,"add","--",*expected,write=True); commit=self._git(root,"commit","-m",f"prometheus: integrate {verification.verification_id}").strip(); sha=self._git(root,"rev-parse","HEAD").strip(); parent=self._git(root,"rev-list","--parents","-n","1",sha).split()
        if len(parent)!=2 or parent[1]!=approval.expected_main_sha: raise SelfDevelopmentGitIntegrationRecoveryRequiredError("Promotion commit verification failed.")
        wt=self.worktree_root/("main-"+sha[:16]); self._git(root,"worktree","add",str(wt),"main",write=True); self._git(wt,"merge","--ff-only",sha,write=True); ifmain=self._git(wt,"rev-parse","HEAD").strip(); self._git(root,"worktree","remove",str(wt),write=True)
        if ifmain!=sha: raise SelfDevelopmentGitIntegrationRecoveryRequiredError("Local main integration failed.")
        receipt=SelfDevelopmentGitIntegrationReceipt(RECEIPT_REVISION,"",self.project_key,verification.workspace_path,approval.approval_id,approval.digest,verification.verification_id,verification.digest,verification.execution_id,verification.execution_digest,branch,"main",approval.expected_main_sha,sha,sha,change_digest,True,False,""); receipt=SelfDevelopmentGitIntegrationReceipt(**{**receipt.to_dict(),"receipt_id":"sdgir_"+_canon({k:v for k,v in receipt.to_dict().items() if k not in {"receipt_id","digest"}})[7:31]}); receipt=SelfDevelopmentGitIntegrationReceipt(**{**receipt.to_dict(),"digest":_canon({k:v for k,v in receipt.to_dict().items() if k!="digest"})}); self.store.append_receipt(receipt)
        payload={"revision":INTEGRATION_REVISION,"project_key":self.project_key,"workspace_path":verification.workspace_path,"approval_id":approval.approval_id,"approval_digest":approval.digest,"verification_id":verification.verification_id,"verification_digest":verification.digest,"source_branch":branch,"target_branch":"main","previous_main_sha":approval.expected_main_sha,"promotion_commit_sha":sha,"resulting_main_sha":sha,"approved_change_set_digest":change_digest,"claim_id":claim.claim_id,"claim_digest":claim.digest,"receipt_id":receipt.receipt_id,"receipt_digest":receipt.digest,"local_integration_completed":True,"remote_publication_performed":False}; iid="sdgi_"+_canon(payload)[7:31]; return SelfDevelopmentGitIntegrationSnapshot(INTEGRATION_REVISION,iid,self.project_key,verification.workspace_path,approval.approval_id,approval.digest,verification.verification_id,verification.digest,branch,"main",approval.expected_main_sha,sha,sha,change_digest,claim.claim_id,claim.digest,receipt.receipt_id,receipt.digest,True,False,_canon({**payload,"integration_id":iid}))
