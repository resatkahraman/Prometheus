from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.workspace.patch_plan import (
    PatchChangeRequest,
    SafePatchPlanBuilder,
    SafePatchPlanError,
    SafePatchPlanMismatch,
    SafePatchPlanStaleError,
)
from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder


def pipeline(root, paths):
    repository_map = RepositoryMapBuilder(project_root=root, workspace_path="a", project_key="a").build()
    lock = ScopeLockBuilder(project_root=root, workspace_path="a", project_key="a").build(
        repository_map=repository_map, allowed_write_paths=paths
    )
    return repository_map, lock


def builder(root, **kwargs):
    return SafePatchPlanBuilder(project_root=root, workspace_path="a", project_key="a", **kwargs)


def test_safe_patch_plan_is_deterministically_sorted(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_bytes(name.encode())
    m, lock = pipeline(tmp_path, ["a.py", "b.py"])
    plan = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("b.py", "replace", "B"), PatchChangeRequest("a.py", "replace", "A")])
    assert [op.path for op in plan.snapshot.operations] == ["a.py", "b.py"]


def test_safe_patch_plan_digest_is_input_order_independent(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_bytes(name.encode())
    m, lock = pipeline(tmp_path, ["a.py", "b.py"])
    requests = [PatchChangeRequest("a.py", "replace", "A"), PatchChangeRequest("b.py", "replace", "B")]
    one = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=requests)
    two = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=list(reversed(requests)))
    assert [operation.path for operation in one.snapshot.operations] == ["a.py", "b.py"]
    assert one.snapshot.operations == two.snapshot.operations
    assert one.snapshot.digest == two.snapshot.digest


def test_safe_patch_plan_snapshot_uses_immutable_tuples(tmp_path):
    (tmp_path / "a.py").write_bytes(b"a")
    m, lock = pipeline(tmp_path, ["a.py"])
    plan = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "delete")])
    assert isinstance(plan.snapshot.operations, tuple)


def test_safe_patch_plan_rejects_empty_operation_set(tmp_path):
    m, lock = pipeline(tmp_path, ["new.py"])
    with pytest.raises(SafePatchPlanError):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[])


def test_safe_patch_plan_create_binds_absent_preimage_and_replacement_hash(tmp_path):
    m, lock = pipeline(tmp_path, ["new.py"])
    plan = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("new.py", "create", "ç")])
    op = plan.snapshot.operations[0]
    assert op.preimage_state == "absent" and op.preimage_sha256 is None and op.replacement_size_bytes == len("ç".encode())
    assert not (tmp_path / "new.py").exists()


def test_safe_patch_plan_replace_binds_exact_file_preimage(tmp_path):
    (tmp_path / "a.py").write_bytes(b"raw\r\n")
    m, lock = pipeline(tmp_path, ["a.py"])
    plan = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "replace", "next")])
    assert plan.snapshot.operations[0].preimage_size_bytes == 5 and (tmp_path / "a.py").read_bytes() == b"raw\r\n"


def test_safe_patch_plan_delete_binds_preimage_without_replacement(tmp_path):
    (tmp_path / "a.py").write_bytes(b"a")
    m, lock = pipeline(tmp_path, ["a.py"])
    plan = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "delete")])
    assert plan.snapshot.operations[0].replacement_sha256 is None and (tmp_path / "a.py").exists()


@pytest.mark.parametrize("operation,text", [("create", None), ("replace", None), ("delete", "x"), ("update", "x")])
def test_safe_patch_plan_rejects_invalid_operation_contract(tmp_path, operation, text):
    m, lock = pipeline(tmp_path, ["a.py"])
    with pytest.raises(SafePatchPlanError):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", operation, text)])


def test_safe_patch_plan_rejects_duplicate_canonical_targets(tmp_path):
    m, lock = pipeline(tmp_path, ["new.py"])
    with pytest.raises(SafePatchPlanError, match="duplicate"):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("new.py", "create", "x"), PatchChangeRequest("./new.py", "create", "y")])


def test_safe_patch_plan_cannot_target_path_outside_scope_lock(tmp_path):
    (tmp_path / "a.py").write_bytes(b"a")
    m, lock = pipeline(tmp_path, [])
    with pytest.raises(SafePatchPlanError, match="outside"):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "delete")])


def test_safe_patch_plan_rejects_tampered_scope_lock(tmp_path):
    m, lock = pipeline(tmp_path, ["new.py"])
    tampered = replace(lock.snapshot, allowed_write_paths=("other.py",))
    lock._snapshot = tampered
    with pytest.raises(SafePatchPlanError, match="integrity"):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("new.py", "create", "x")])


def test_safe_patch_plan_rejects_byte_identical_replacement(tmp_path):
    (tmp_path / "a.py").write_bytes(b"same")
    m, lock = pipeline(tmp_path, ["a.py"])
    with pytest.raises(SafePatchPlanError, match="does not change"):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "replace", "same")])


def test_safe_patch_plan_assert_current_and_change(tmp_path):
    (tmp_path / "a.py").write_bytes(b"a")
    m, lock = pipeline(tmp_path, ["a.py"])
    plan = builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "replace", "b")])
    plan.assert_current()
    assert plan.assert_change(path="a.py", operation="replace", replacement_text="b").path == "a.py"
    with pytest.raises(SafePatchPlanMismatch):
        plan.assert_change(path="a.py", operation="replace", replacement_text="c")
    (tmp_path / "a.py").write_bytes(b"changed")
    with pytest.raises(SafePatchPlanStaleError):
        plan.assert_current()


def test_safe_patch_plan_rejects_existing_target_not_in_map(tmp_path):
    m = RepositoryMapBuilder(project_root=tmp_path, workspace_path="a", project_key="a").build()
    lock = ScopeLockBuilder(project_root=tmp_path, workspace_path="a", project_key="a").build(repository_map=m, allowed_write_paths=["late.py"])
    (tmp_path / "late.py").write_bytes(b"x")
    with pytest.raises(SafePatchPlanError, match="not present"):
        builder(tmp_path).build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("late.py", "replace", "y")])


def test_safe_patch_plan_from_runtime_remains_bound(tmp_path):
    root = tmp_path / "a"; root.mkdir(); (root / "a.py").write_bytes(b"a")
    runtime = SimpleNamespace(project_root=root, workspace_path="a", project_key="a")
    from app.core.config import Settings
    plan_builder = SafePatchPlanBuilder.from_runtime(runtime, settings=Settings(workspace_root=tmp_path))
    m, lock = pipeline(root, ["a.py"])
    plan = plan_builder.build(repository_map=m, scope_lock=lock, changes=[PatchChangeRequest("a.py", "delete")])
    assert plan.snapshot.workspace_path == "a"
