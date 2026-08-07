from __future__ import annotations

import ast
import hashlib
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import ToolError
from app.workspace.patch_plan import PatchChangeRequest, SafePatchPlan, SafePatchPlanBuilder
from app.workspace.policy import WorkspacePolicy
from app.workspace.repository_map import REPOSITORY_MAP_REVISION, RepositoryMapSnapshot
from app.workspace.scope_lock import ScopeLock, ScopeLockViolation
from app.workspace.structural_patch import PythonStructuralPatchRequest, PythonSymbolSelector, _KIND_NODES, _line_info, _resolve_symbol

PYTHON_STRUCTURAL_PATCH_SET_REVISION = "python-structural-patch-set-v1"


class PythonStructuralPatchSetError(ValueError):
    pass


class PythonStructuralPatchSetStaleError(PythonStructuralPatchSetError):
    pass


@dataclass(frozen=True)
class PythonStructuralPatchSetEditSnapshot:
    path: str; symbol_path: tuple[str, ...]; symbol_kind: str; start_line: int; end_line: int; start_offset: int; end_offset: int
    original_span_sha256: str; original_span_size_bytes: int; replacement_span_sha256: str; replacement_span_size_bytes: int
    def to_dict(self):
        return {"path":self.path,"symbol_path":list(self.symbol_path),"symbol_kind":self.symbol_kind,"start_line":self.start_line,"end_line":self.end_line,"start_offset":self.start_offset,"end_offset":self.end_offset,"original_span_sha256":self.original_span_sha256,"original_span_size_bytes":self.original_span_size_bytes,"replacement_span_sha256":self.replacement_span_sha256,"replacement_span_size_bytes":self.replacement_span_size_bytes}


@dataclass(frozen=True)
class PythonStructuralPatchSetFileSnapshot:
    path: str; base_sha256: str; base_size_bytes: int; output_sha256: str; output_size_bytes: int; edits: tuple[PythonStructuralPatchSetEditSnapshot, ...]; edit_count: int
    def to_dict(self):
        return {"path":self.path,"base_sha256":self.base_sha256,"base_size_bytes":self.base_size_bytes,"output_sha256":self.output_sha256,"output_size_bytes":self.output_size_bytes,"edits":[e.to_dict() for e in self.edits],"edit_count":self.edit_count}


@dataclass(frozen=True)
class PythonStructuralPatchSetSnapshot:
    revision: str; workspace_path: str; project_key: str; files: tuple[PythonStructuralPatchSetFileSnapshot, ...]; file_count: int; edit_count: int; safe_patch_plan_digest: str; digest: str
    def to_dict(self):
        return {"revision":self.revision,"workspace_path":self.workspace_path,"project_key":self.project_key,"files":[f.to_dict() for f in self.files],"file_count":self.file_count,"edit_count":self.edit_count,"safe_patch_plan_digest":self.safe_patch_plan_digest,"digest":self.digest}


@dataclass(frozen=True)
class CompiledPythonStructuralPatchSet:
    snapshot: PythonStructuralPatchSetSnapshot
    plan: SafePatchPlan
    changes: tuple[PatchChangeRequest, ...]


def _hash(data: bytes): return "sha256:" + hashlib.sha256(data).hexdigest()
def _digest(payload): return _hash(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _verify_map(repository_map: RepositoryMapSnapshot) -> None:
    try:
        if repository_map.revision != REPOSITORY_MAP_REVISION or repository_map.entry_count != len(repository_map.entries) or repository_map.truncated or repository_map.depth_truncated:
            raise ValueError
        paths = [entry.path for entry in repository_map.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError
        payload = repository_map.to_dict(); digest = payload.pop("digest", None)
        if _digest(payload) != digest:
            raise ValueError
    except Exception:
        raise PythonStructuralPatchSetError("Repository map integrity check failed.") from None


class PythonStructuralPatchSetCompiler:
    def __init__(self, *, project_root: Path, workspace_path: str, project_key: str, max_file_bytes: int = 1_048_576, max_edits: int = 128, max_operations: int = 128, max_search_results: int = 1_000):
        root=Path(project_root).expanduser()
        if not root.exists() or not root.is_dir() or root.is_symlink() or not workspace_path or not project_key or max_file_bytes<=0 or not 1<=max_edits<=1024 or not 1<=max_operations<=1024: raise PythonStructuralPatchSetError("Structural patch set construction is invalid.")
        self.project_root=root.resolve(); self.workspace_path=workspace_path; self.project_key=project_key; self.max_file_bytes=max_file_bytes; self.max_edits=max_edits; self.max_operations=max_operations
        self.policy=WorkspacePolicy(root=self.project_root,max_file_bytes=max_file_bytes,max_search_results=max_search_results)

    @classmethod
    def from_runtime(cls,runtime,*,settings,max_edits=128,max_operations=128):
        return cls(project_root=runtime.project_root,workspace_path=runtime.workspace_path,project_key=runtime.project_key,max_file_bytes=settings.workspace_max_file_bytes,max_edits=max_edits,max_operations=max_operations,max_search_results=settings.workspace_max_search_results)

    def compile(self, *, repository_map: RepositoryMapSnapshot, scope_lock: ScopeLock, requests):
        _verify_map(repository_map)
        reqs=list(requests)
        if not reqs: raise PythonStructuralPatchSetError("Structural patch set must contain at least one edit.")
        if len(reqs)>self.max_edits: raise PythonStructuralPatchSetError("Structural patch set exceeds the edit limit.")
        if (repository_map.workspace_path,repository_map.project_key)!=(self.workspace_path,self.project_key) or (scope_lock.snapshot.workspace_path,scope_lock.snapshot.project_key)!=(self.workspace_path,self.project_key): raise PythonStructuralPatchSetError("Structural patch set inputs do not match the bound project.")
        grouped={}; seen=set()
        for req in reqs:
            try: path=scope_lock.assert_write(req.path)
            except ScopeLockViolation: raise PythonStructuralPatchSetError("Structural patch target is outside the authorized scope.") from None
            key=(path,req.selector.symbol_path,req.selector.symbol_kind)
            if key in seen: raise PythonStructuralPatchSetError("Structural patch set contains a duplicate symbol target.")
            seen.add(key); grouped.setdefault(path,[]).append(req)
        files=[]; changes=[]
        for path, items in sorted(grouped.items()):
            entry=next((e for e in repository_map.entries if e.path==path),None)
            if entry is None or entry.suffix!=".py" or entry.role not in {"source","test"}: raise PythonStructuralPatchSetError("Structural patch target must be an existing Python repository file.")
            try: target=self.policy.resolve(path,must_exist=True)
            except (ToolError,OSError,ValueError): raise PythonStructuralPatchSetError("Structural patch target must be an existing Python repository file.") from None
            if target.is_symlink() or not target.is_file(): raise PythonStructuralPatchSetError("Structural patch target must be an existing Python repository file.")
            raw=target.read_bytes()
            if len(raw)>self.max_file_bytes or raw.startswith(b"\xef\xbb\xbf") or b"\0" in raw: raise PythonStructuralPatchSetError("Structural patch requires BOM-free UTF-8 Python source.")
            try: source=raw.decode("utf-8")
            except UnicodeDecodeError: raise PythonStructuralPatchSetError("Structural patch requires BOM-free UTF-8 Python source.") from None
            try: ending,starts,lines=_line_info(raw); tree=ast.parse(source)
            except Exception: raise PythonStructuralPatchSetError("Structural patch target is not valid Python source.") from None
            spans=[]
            for req in items:
                try: node=_resolve_symbol(tree,req.selector)
                except Exception as exc: raise PythonStructuralPatchSetError(str(exc)) from None
                start=min([node.lineno]+[d.lineno for d in getattr(node,"decorator_list",[])])
                end=node.end_lineno
                parent_body=tree.body
                if len(req.selector.symbol_path)>1:
                    parent=_resolve_symbol(tree,PythonSymbolSelector(req.selector.symbol_path[:-1],"class")); parent_body=parent.body
                for sibling in parent_body:
                    if sibling is not node and hasattr(sibling,"end_lineno") and sibling.lineno<=end and sibling.end_lineno>=start: raise PythonStructuralPatchSetError("Structural patch target does not occupy an isolated source span.")
                so=starts[start-1]; eo=starts[end-1]+len(lines[end-1]); orig=raw[so:eo]
                repl=req.replacement_source
                if not isinstance(repl,str) or not repl or "\0" in repl: raise PythonStructuralPatchSetError("Structural replacement is invalid.")
                if "\r" in repl.replace("\r\n", ""):
                    raise PythonStructuralPatchSetError("Structural replacement has invalid line endings.")
                norm=repl.replace("\r\n","\n"); first=next((x for x in norm.split("\n") if x.strip()),"")
                target_line=lines[start-1]; tp=target_line[:len(target_line)-len(target_line.lstrip(b" \t"))].decode("ascii"); rp=first[:len(first)-len(first.lstrip(" \t"))]
                if tp!=rp: raise PythonStructuralPatchSetError("Structural replacement indentation does not match the target.")
                try: rt=ast.parse(textwrap.dedent(norm))
                except SyntaxError: raise PythonStructuralPatchSetError("Structural replacement is not valid Python source.") from None
                if len(rt.body)!=1 or type(rt.body[0]) is not type(node) or rt.body[0].name!=node.name: raise PythonStructuralPatchSetError("Structural replacement does not preserve symbol identity.")
                body=norm.replace("\n",ending) if ending else norm
                if orig.endswith((b"\n",b"\r\n")) and not body.endswith(ending): body+=ending
                if not orig.endswith((b"\n",b"\r\n")): body=body.rstrip("\r\n")
                rb=body.encode("utf-8")
                if rb==orig: raise PythonStructuralPatchSetError("Structural replacement makes no change.")
                spans.append((so,eo,rb,req,start,end,orig))
            spans.sort(key=lambda x:(x[0],x[1]))
            if any(a[1]>b[0] for a,b in zip(spans,spans[1:])): raise PythonStructuralPatchSetError("Structural patch set contains overlapping targets.")
            out=raw
            for so,eo,rb,*_ in reversed(spans): out=out[:so]+rb+out[eo:]
            try: ast.parse(out.decode("utf-8"))
            except Exception: raise PythonStructuralPatchSetError("Structural patch set output is not valid Python source.") from None
            edits_list = []
            for start_offset, end_offset, replacement_bytes, request, start_line, end_line, original_span in sorted(
                spans,
                key=lambda item: (item[0], item[1], item[3].selector.symbol_path, item[3].selector.symbol_kind),
            ):
                edits_list.append(
                    PythonStructuralPatchSetEditSnapshot(
                        path=path,
                        symbol_path=request.selector.symbol_path,
                        symbol_kind=request.selector.symbol_kind,
                        start_line=start_line,
                        end_line=end_line,
                        start_offset=start_offset,
                        end_offset=end_offset,
                        original_span_sha256=_hash(original_span),
                        original_span_size_bytes=len(original_span),
                        replacement_span_sha256=_hash(replacement_bytes),
                        replacement_span_size_bytes=len(replacement_bytes),
                    )
                )
            edits=tuple(edits_list)
            files.append(PythonStructuralPatchSetFileSnapshot(path,_hash(raw),len(raw),_hash(out),len(out),edits,len(edits))); changes.append(PatchChangeRequest(path,"replace",out.decode("utf-8")))
        if len(files)>self.max_operations: raise PythonStructuralPatchSetError("Structural patch set exceeds the operation limit.")
        plan=SafePatchPlanBuilder(project_root=self.project_root,workspace_path=self.workspace_path,project_key=self.project_key,max_file_bytes=self.max_file_bytes,max_operations=self.max_operations).build(repository_map=repository_map,scope_lock=scope_lock,changes=tuple(changes))
        for file,op in zip(files,plan.snapshot.operations):
            if op.preimage_sha256!=file.base_sha256 or op.preimage_size_bytes!=file.base_size_bytes or op.replacement_sha256!=file.output_sha256 or op.replacement_size_bytes!=file.output_size_bytes: raise PythonStructuralPatchSetStaleError("Structural patch set source changed during compilation.")
        files=tuple(files); payload={"revision":PYTHON_STRUCTURAL_PATCH_SET_REVISION,"workspace_path":self.workspace_path,"project_key":self.project_key,"files":[f.to_dict() for f in files],"file_count":len(files),"edit_count":sum(f.edit_count for f in files),"safe_patch_plan_digest":plan.snapshot.digest}
        snap=PythonStructuralPatchSetSnapshot(PYTHON_STRUCTURAL_PATCH_SET_REVISION,self.workspace_path,self.project_key,files,len(files),sum(f.edit_count for f in files),plan.snapshot.digest,_digest(payload))
        return CompiledPythonStructuralPatchSet(snap,plan,tuple(changes))
