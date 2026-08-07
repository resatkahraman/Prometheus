import pytest

from app.workspace.patch_approval import SafePatchApprovalBuilder, SafePatchApprovalError, SafePatchApprovalMismatch, SafePatchApprovalStaleError
from app.workspace.patch_plan import PatchChangeRequest, SafePatchPlanBuilder
from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder


def pipeline(root, path, op, text=None):
    m=RepositoryMapBuilder(project_root=root,workspace_path="a",project_key="a").build(); lock=ScopeLockBuilder(project_root=root,workspace_path="a",project_key="a").build(repository_map=m,allowed_write_paths=[path]); plan=SafePatchPlanBuilder(project_root=root,workspace_path="a",project_key="a").build(repository_map=m,scope_lock=lock,changes=[PatchChangeRequest(path,op,text)]); return plan


def test_safe_patch_approval_replace_preview_and_binding(tmp_path):
    (tmp_path/"a.py").write_text("value = 1\n")
    plan=pipeline(tmp_path,"a.py","replace","value = 2\n"); b=SafePatchApprovalBuilder(project_root=tmp_path,workspace_path="a",project_key="a"); prepared=b.prepare(plan=plan,changes=[PatchChangeRequest("a.py","replace","value = 2\n")])
    assert prepared.preview.operations[0].added_lines==1 and prepared.preview.operations[0].removed_lines==1; assert prepared.binding.preview_digest==prepared.preview.digest; b.assert_binding(plan=plan,changes=[PatchChangeRequest("a.py","replace","value = 2\n")],preview=prepared.preview,binding=prepared.binding)


def test_safe_patch_approval_create_and_delete(tmp_path):
    plan=pipeline(tmp_path,"new.py","create","x\n"); b=SafePatchApprovalBuilder(project_root=tmp_path,workspace_path="a",project_key="a"); p=b.prepare(plan=plan,changes=[PatchChangeRequest("new.py","create","x\n")]); assert p.preview.operations[0].preimage_state=="absent"; assert not (tmp_path/"new.py").exists()
    (tmp_path/"old.py").write_text("x\n"); plan2=pipeline(tmp_path,"old.py","delete"); p2=b.prepare(plan=plan2,changes=[PatchChangeRequest("old.py","delete")]); assert p2.preview.operations[0].replacement_sha256 is None and (tmp_path/"old.py").exists()


def test_safe_patch_approval_rejects_stale(tmp_path):
    (tmp_path/"a.py").write_text("x\n"); plan=pipeline(tmp_path,"a.py","replace","y\n"); b=SafePatchApprovalBuilder(project_root=tmp_path,workspace_path="a",project_key="a"); (tmp_path/"a.py").write_text("z\n")
    with pytest.raises(SafePatchApprovalStaleError): b.prepare(plan=plan,changes=[PatchChangeRequest("a.py","replace","y\n")])


def test_safe_patch_approval_binding_is_content_free(tmp_path):
    (tmp_path/"a.py").write_text("UNIQUE_SOURCE\n"); plan=pipeline(tmp_path,"a.py","replace","UNIQUE_REPLACEMENT\n"); b=SafePatchApprovalBuilder(project_root=tmp_path,workspace_path="a",project_key="a"); p=b.prepare(plan=plan,changes=[PatchChangeRequest("a.py","replace","UNIQUE_REPLACEMENT\n")]); data=str(p.binding.to_dict()); assert "UNIQUE_SOURCE" not in data and "UNIQUE_REPLACEMENT" not in data and "diff" not in data


def test_safe_patch_approval_rejects_tampered_preview(tmp_path):
    (tmp_path/"a.py").write_text("x\n"); plan=pipeline(tmp_path,"a.py","replace","y\n"); b=SafePatchApprovalBuilder(project_root=tmp_path,workspace_path="a",project_key="a"); p=b.prepare(plan=plan,changes=[PatchChangeRequest("a.py","replace","y\n")]); from dataclasses import replace; tampered=replace(p.preview,total_diff_chars=p.preview.total_diff_chars+1)
    with pytest.raises(SafePatchApprovalMismatch): b.assert_binding(plan=plan,changes=[PatchChangeRequest("a.py","replace","y\n")],preview=tampered,binding=p.binding)
