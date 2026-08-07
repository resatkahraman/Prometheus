from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.workspace.repository_map import RepositoryMapBuilder, RepositoryMapError


def builder(root: Path, **kwargs):
    return RepositoryMapBuilder(project_root=root, workspace_path="projects/a", project_key="a", **kwargs)


def test_repository_map_is_deterministically_sorted(tmp_path):
    (tmp_path / "z.py").write_text("z", encoding="utf-8")
    (tmp_path / "a.py").write_text("a", encoding="utf-8")
    assert [e.path for e in builder(tmp_path).build().entries] == ["a.py", "z.py"]


def test_repository_map_same_metadata_produces_same_digest(tmp_path):
    (tmp_path / "a.py").write_text("marker", encoding="utf-8")
    a, b = builder(tmp_path).build(), builder(tmp_path).build()
    assert a == b and a.digest.startswith("sha256:")


def test_repository_map_exposes_only_project_relative_paths(tmp_path):
    (tmp_path / "a.py").write_text(str(tmp_path), encoding="utf-8")
    snapshot = builder(tmp_path).build()
    assert all(not Path(e.path).is_absolute() and "\\" not in e.path and not e.path.startswith("..") for e in snapshot.entries)
    assert str(tmp_path) not in str(snapshot.to_dict())


def test_repository_map_classifies_source_test_config_docs_and_other(tmp_path):
    for path in ("app/main.py", "tests/test_main.py", "pyproject.toml", "docs/README.md", "assets/logo.bin"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
    roles = {e.path: e.role for e in builder(tmp_path).build().entries}
    assert roles == {"app/main.py": "source", "assets/logo.bin": "other", "docs/README.md": "docs", "pyproject.toml": "config", "tests/test_main.py": "test"}


def test_repository_map_ignores_internal_and_generated_directories(tmp_path):
    for name in (".git", ".adam", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"):
        target = tmp_path / name / "x.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    visible = tmp_path / ".github/workflows/ci.yml"
    visible.parent.mkdir(parents=True)
    visible.write_text("x", encoding="utf-8")
    paths = {e.path for e in builder(tmp_path).build().entries}
    assert paths == {".github/workflows/ci.yml"}


def test_repository_map_hard_entry_cap_sets_truncated(tmp_path):
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    snapshot = builder(tmp_path, max_entries=2).build()
    assert len(snapshot.entries) == 2 and snapshot.truncated


def test_repository_map_exact_entry_cap_is_not_truncated(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    snapshot = builder(tmp_path, max_entries=1).build()
    assert len(snapshot.entries) == 1 and not snapshot.truncated


def test_repository_map_depth_cap_is_deterministic(tmp_path):
    (tmp_path / "a" / "b" / "deep.py").parent.mkdir(parents=True)
    (tmp_path / "a" / "b" / "deep.py").write_text("x", encoding="utf-8")
    (tmp_path / "root.py").write_text("x", encoding="utf-8")
    snapshot = builder(tmp_path, max_depth=2).build()
    assert "root.py" in {e.path for e in snapshot.entries}
    assert "a/b/deep.py" not in {e.path for e in snapshot.entries} and snapshot.depth_truncated


def test_repository_map_empty_repository_is_valid(tmp_path):
    snapshot = builder(tmp_path).build()
    assert snapshot.entries == () and snapshot.entry_count == 0 and not snapshot.truncated


def test_repository_map_key_path_annotation_is_component_aware(tmp_path):
    for path in ("app/core/config.py", "application/config.py"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    entries = {e.path: e.is_key_path for e in builder(tmp_path).build(key_paths=["app"]).entries}
    assert entries["app/core/config.py"] and not entries["application/config.py"]


def test_repository_map_protected_path_annotation_is_component_aware(tmp_path):
    for path in ("app/security/policy.py", "app/security_old/policy.py"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    entries = {e.path: e.is_protected_path for e in builder(tmp_path).build(protected_paths=["app/security"]).entries}
    assert entries["app/security/policy.py"] and not entries["app/security_old/policy.py"]


def test_repository_map_does_not_follow_symlink_outside_project(tmp_path):
    outside = tmp_path.parent / "repository-map-outside-file.py"
    outside.write_text("x", encoding="utf-8")
    try:
        (tmp_path / "escape.py").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert "escape.py" not in {e.path for e in builder(tmp_path).build().entries}


def test_repository_map_does_not_follow_directory_symlinks(tmp_path):
    outside = tmp_path.parent / "repository-map-outside-dir"
    outside.mkdir(exist_ok=True)
    (outside / "secret.py").write_text("x", encoding="utf-8")
    try:
        (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert not any(e.path.startswith("linked/") for e in builder(tmp_path).build().entries)


def test_repository_map_fails_closed_for_path_over_configured_limit(tmp_path):
    target = tmp_path / ("x" * 20 + ".py")
    target.write_text("x", encoding="utf-8")
    with pytest.raises(RepositoryMapError, match="Repository path exceeds configured mapping limit"):
        builder(tmp_path, max_path_chars=10).build()


def test_repository_map_snapshot_contains_metadata_not_file_contents(tmp_path):
    marker = "UNIQUE_REPOSITORY_MARKER"
    (tmp_path / "a.py").write_text(marker, encoding="utf-8")
    snapshot = builder(tmp_path).build()
    assert marker not in str(snapshot.to_dict()) and marker not in snapshot.digest


def test_repository_map_is_bound_to_selected_project_root(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "a.py").write_text("x", encoding="utf-8")
    (b / "b.py").write_text("x", encoding="utf-8")
    paths = {e.path for e in RepositoryMapBuilder(project_root=a, workspace_path="a", project_key="a").build().entries}
    assert paths == {"a.py"}


def test_repository_map_from_runtime_remains_bound_after_active_project_changes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "a.py").write_text("x", encoding="utf-8")
    (b / "b.py").write_text("x", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    runtime = SimpleNamespace(project_root=a, workspace_path="a", project_key="a")
    mapper = RepositoryMapBuilder.from_runtime(runtime, settings=settings)
    runtime.project_root = b
    snapshot = mapper.build()
    assert snapshot.workspace_path == "a" and snapshot.project_key == "a" and {e.path for e in snapshot.entries} == {"a.py"}


def test_repository_map_does_not_mutate_cwd_or_settings(tmp_path):
    settings = Settings(workspace_root=tmp_path)
    cwd = Path.cwd()
    root = settings.workspace_root
    builder(tmp_path).build()
    assert Path.cwd() == cwd and settings.workspace_root == root
