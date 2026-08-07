from pathlib import Path
from types import SimpleNamespace

import pytest

from app.workspace.patch_executor import (
    SafePatchExecutionError,
    SafePatchExecutionStaleError,
    SafePatchExecutor,
)
from app.workspace.patch_plan import PatchChangeRequest, SafePatchPlanBuilder
from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder


def pipeline(root, allowed):
    m = RepositoryMapBuilder(project_root=root, workspace_path="a", project_key="a").build()
    lock = ScopeLockBuilder(project_root=root, workspace_path="a", project_key="a").build(repository_map=m, allowed_write_paths=allowed)
    return m, lock


def plan(root, allowed, changes):
    m, lock = pipeline(root, allowed)
    p = SafePatchPlanBuilder(project_root=root, workspace_path="a", project_key="a").build(repository_map=m, scope_lock=lock, changes=changes)
    return p, lock


def test_safe_patch_executor_create_success(tmp_path):
    p, _ = plan(tmp_path, ["new.py"], [PatchChangeRequest("new.py", "create", "ç" )])
    receipt = SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[PatchChangeRequest("new.py", "create", "ç")])
    assert (tmp_path / "new.py").read_bytes() == "ç".encode("utf-8")
    assert receipt.operations[0].result_state == "file"


def test_safe_patch_executor_replace_success(tmp_path):
    (tmp_path / "a.py").write_bytes(b"old")
    p, _ = plan(tmp_path, ["a.py"], [PatchChangeRequest("a.py", "replace", "new")])
    receipt = SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[PatchChangeRequest("a.py", "replace", "new")])
    assert (tmp_path / "a.py").read_bytes() == b"new" and receipt.operations[0].result_size_bytes == 3


def test_safe_patch_executor_delete_success(tmp_path):
    (tmp_path / "a.py").write_bytes(b"old")
    p, _ = plan(tmp_path, ["a.py"], [PatchChangeRequest("a.py", "delete")])
    receipt = SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[PatchChangeRequest("a.py", "delete")])
    assert not (tmp_path / "a.py").exists() and receipt.operations[0].result_state == "absent"


def test_safe_patch_executor_payload_must_cover_plan(tmp_path):
    p, _ = plan(tmp_path, ["new.py"], [PatchChangeRequest("new.py", "create", "x")])
    with pytest.raises(SafePatchExecutionError):
        SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[])
    assert not (tmp_path / "new.py").exists()


def test_safe_patch_executor_payload_order_is_irrelevant(tmp_path):
    (tmp_path / "a.py").write_bytes(b"a")
    (tmp_path / "b.py").write_bytes(b"b")
    m, lock = pipeline(tmp_path, ["a.py", "b.py"])
    changes = [PatchChangeRequest("a.py", "replace", "A"), PatchChangeRequest("b.py", "replace", "B")]
    p = SafePatchPlanBuilder(project_root=tmp_path, workspace_path="a", project_key="a").build(repository_map=m, scope_lock=lock, changes=changes)
    receipt = SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=list(reversed(changes)))
    assert [op.path for op in receipt.operations] == ["a.py", "b.py"]


def test_safe_patch_executor_stale_before_staging(tmp_path):
    (tmp_path / "a.py").write_bytes(b"a")
    p, _ = plan(tmp_path, ["a.py"], [PatchChangeRequest("a.py", "replace", "A")])
    (tmp_path / "a.py").write_bytes(b"changed")
    with pytest.raises(SafePatchExecutionStaleError):
        SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[PatchChangeRequest("a.py", "replace", "A")])


def test_safe_patch_executor_second_execution_is_stale(tmp_path):
    p, _ = plan(tmp_path, ["new.py"], [PatchChangeRequest("new.py", "create", "x")])
    executor = SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a")
    change = PatchChangeRequest("new.py", "create", "x")
    executor.execute(plan=p, changes=[change])
    with pytest.raises(SafePatchExecutionStaleError):
        executor.execute(plan=p, changes=[change])


def test_safe_patch_executor_parent_directory_missing(tmp_path):
    p, _ = plan(tmp_path, ["missing/new.py"], [PatchChangeRequest("missing/new.py", "create", "x")])
    with pytest.raises(SafePatchExecutionError, match="parent"):
        SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[PatchChangeRequest("missing/new.py", "create", "x")])
    assert not (tmp_path / "missing").exists()


def test_safe_patch_executor_receipt_contains_no_content_or_absolute_path(tmp_path):
    marker = "UNIQUE_EXECUTOR_MARKER"
    p, _ = plan(tmp_path, ["new.py"], [PatchChangeRequest("new.py", "create", marker)])
    receipt = SafePatchExecutor(project_root=tmp_path, workspace_path="a", project_key="a").execute(plan=p, changes=[PatchChangeRequest("new.py", "create", marker)])
    assert marker not in str(receipt.to_dict()) and str(tmp_path) not in str(receipt.to_dict())


def test_safe_patch_executor_from_runtime_remains_bound(tmp_path):
    root = tmp_path / "a"; root.mkdir()
    runtime = SimpleNamespace(project_root=root, workspace_path="a", project_key="a")
    from app.core.config import Settings
    executor = SafePatchExecutor.from_runtime(runtime, settings=Settings(workspace_root=tmp_path))
    assert executor.workspace_path == "a" and executor.project_root == root
