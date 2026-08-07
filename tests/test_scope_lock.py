from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder, ScopeLockError, ScopeLockViolation


def _map(root):
    return RepositoryMapBuilder(project_root=root, workspace_path="a", project_key="a").build()


def _builder(root):
    return ScopeLockBuilder(project_root=root, workspace_path="a", project_key="a")


def test_scope_lock_is_deterministic_and_sorted(tmp_path):
    (tmp_path / "a.py").write_text("x")
    m = _map(tmp_path)
    one = _builder(tmp_path).build(repository_map=m, allowed_write_paths=["z.py", "a.py", "z.py"])
    two = _builder(tmp_path).build(repository_map=m, allowed_write_paths=["a.py", "z.py"])
    assert one.snapshot.allowed_write_paths == ("a.py", "z.py")
    assert one.snapshot.digest == two.snapshot.digest


def test_empty_scope_lock_denies_all_writes(tmp_path):
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=[])
    assert lock.snapshot.allowed_write_paths == () and lock.snapshot.write_path_count == 0
    assert not lock.allows_write("app/main.py")
    with pytest.raises(ScopeLockViolation):
        lock.assert_write("app/main.py")


def test_scope_lock_snapshot_contains_no_absolute_project_root(tmp_path):
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=[])
    assert str(tmp_path) not in str(lock.snapshot.to_dict())


def test_scope_lock_rejects_repository_map_from_another_project(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    with pytest.raises(ScopeLockError, match="does not match"):
        _builder(a).build(repository_map=RepositoryMapBuilder(project_root=b, workspace_path="b", project_key="b").build(), allowed_write_paths=[])


def test_scope_lock_rejects_tampered_repository_map_digest(tmp_path):
    tampered = replace(_map(tmp_path), digest="sha256:" + "0" * 64)
    with pytest.raises(ScopeLockError, match="integrity"):
        _builder(tmp_path).build(repository_map=tampered, allowed_write_paths=[])


def test_scope_lock_rejects_truncated_repository_map(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("x")
    m = RepositoryMapBuilder(project_root=tmp_path, workspace_path="a", project_key="a", max_entries=1).build()
    assert m.truncated is True
    with pytest.raises(ScopeLockError, match="incomplete"):
        _builder(tmp_path).build(repository_map=m, allowed_write_paths=[])


def test_scope_lock_rejects_depth_truncated_repository_map(tmp_path):
    target = tmp_path / "a" / "deep.py"
    target.parent.mkdir(parents=True)
    target.write_text("x")
    m = RepositoryMapBuilder(project_root=tmp_path, workspace_path="a", project_key="a", max_depth=1).build()
    assert m.depth_truncated is True
    with pytest.raises(ScopeLockError, match="incomplete"):
        _builder(tmp_path).build(repository_map=m, allowed_write_paths=[])


def test_scope_lock_allows_exact_existing_repository_file(tmp_path):
    (tmp_path / "app.py").write_text("x")
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=["app.py"])
    assert lock.assert_write("./app.py") == "app.py"


def test_scope_lock_can_authorize_new_missing_file(tmp_path):
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=["new.py"])
    assert lock.assert_write("new.py") == "new.py"


def test_scope_lock_rejects_existing_target_missing_from_map(tmp_path):
    m = _map(tmp_path)
    (tmp_path / "late.py").write_text("x")
    with pytest.raises(ScopeLockError, match="not present"):
        _builder(tmp_path).build(repository_map=m, allowed_write_paths=["late.py"])


def test_scope_lock_rejects_directory_as_writable_target(tmp_path):
    (tmp_path / "app").mkdir()
    with pytest.raises(ScopeLockError, match="directories"):
        _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=["app"])


def test_scope_lock_protected_matching_is_component_aware(tmp_path):
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app/security_old.py").write_text("x")
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), protected_paths=["app/security"], allowed_write_paths=["app/security_old.py"])
    assert lock.allows_write("app/security_old.py")


def test_scope_lock_rejects_protected_subtree(tmp_path):
    (tmp_path / "app/security/auth.py").parent.mkdir(parents=True)
    (tmp_path / "app/security/auth.py").write_text("x")
    with pytest.raises(ScopeLockError, match="Protected"):
        _builder(tmp_path).build(repository_map=_map(tmp_path), protected_paths=["app/security"], allowed_write_paths=["app/security/auth.py"])


@pytest.mark.parametrize("path", ["../outside.py", "nested/../../outside.py", "", ".", "/outside.py"])
def test_scope_lock_rejects_unsafe_write_paths(tmp_path, path):
    with pytest.raises(ScopeLockError):
        _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=[path])


def test_scope_lock_runtime_authorization_is_exact(tmp_path):
    (tmp_path / "app/main.py").parent.mkdir()
    (tmp_path / "app/main.py").write_text("x")
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=["app/main.py"])
    assert lock.allows_write("app/main.py") and lock.allows_write("app\\main.py")
    assert not lock.allows_write("app/other.py")
    assert not lock.allows_write("app/main.py.bak")


def test_scope_lock_snapshot_uses_immutable_tuples(tmp_path):
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=["new.py"], protected_paths=["safe"])
    assert isinstance(lock.snapshot.allowed_write_paths, tuple)
    with pytest.raises((AttributeError, TypeError)):
        lock.snapshot.allowed_write_paths += ("x",)


def test_scope_lock_from_runtime_remains_bound_after_active_project_changes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir(); (a / "a.py").write_text("x"); (b / "b.py").write_text("x")
    settings = Settings(workspace_root=tmp_path)
    runtime = SimpleNamespace(project_root=a, workspace_path="a", project_key="a")
    builder = ScopeLockBuilder.from_runtime(runtime, settings=settings)
    lock = builder.build(repository_map=_map(a), allowed_write_paths=["a.py"])
    runtime.project_root = b
    assert lock.allows_write("a.py") and not lock.allows_write("b.py")


def test_scope_lock_does_not_mutate_cwd_or_settings(tmp_path):
    settings = Settings(workspace_root=tmp_path)
    cwd, root = Path.cwd(), settings.workspace_root
    _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=[])
    assert Path.cwd() == cwd and settings.workspace_root == root


def test_scope_lock_snapshot_contains_only_scope_metadata(tmp_path):
    (tmp_path / "a.py").write_text("UNIQUE_MARKER")
    lock = _builder(tmp_path).build(repository_map=_map(tmp_path), allowed_write_paths=["a.py"])
    assert "UNIQUE_MARKER" not in str(lock.snapshot.to_dict())
