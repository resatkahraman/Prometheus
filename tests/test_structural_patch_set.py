import pytest

from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder
from app.workspace.structural_patch import PythonStructuralPatchRequest, PythonSymbolSelector
from app.workspace.structural_patch_set import PythonStructuralPatchSetCompiler, PythonStructuralPatchSetError


def pipeline(root, paths):
    m = RepositoryMapBuilder(project_root=root, workspace_path="a", project_key="a").build()
    lock = ScopeLockBuilder(project_root=root, workspace_path="a", project_key="a").build(repository_map=m, allowed_write_paths=paths)
    return m, lock


def test_structural_patch_set_two_methods_same_file(tmp_path):
    (tmp_path / "mod.py").write_text("class S:\n    def alpha(self):\n        return 1\n    def beta(self):\n        return 2\n    def keep(self):\n        return 3\n")
    m, lock = pipeline(tmp_path, ["mod.py"])
    req = [PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("S", "alpha"), "function"), "    def alpha(self):\n        return 10"), PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("S", "beta"), "function"), "    def beta(self):\n        return 20")]
    result = PythonStructuralPatchSetCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, requests=req)
    assert len(result.changes) == len(result.plan.snapshot.operations) == 1
    assert "return 10" in result.changes[0].replacement_text and "return 20" in result.changes[0].replacement_text and "return 3" in result.changes[0].replacement_text


def test_structural_patch_set_multiple_files(tmp_path):
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_text("def run():\n    return 1\n")
    m, lock = pipeline(tmp_path, ["a.py", "b.py"])
    req = [PythonStructuralPatchRequest("b.py", PythonSymbolSelector(("run",), "function"), "def run():\n    return 2"), PythonStructuralPatchRequest("a.py", PythonSymbolSelector(("run",), "function"), "def run():\n    return 3")]
    result = PythonStructuralPatchSetCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, requests=req)
    assert [c.path for c in result.changes] == ["a.py", "b.py"] and result.snapshot.file_count == 2


def test_structural_patch_set_rejects_duplicate_and_overlap(tmp_path):
    (tmp_path / "mod.py").write_text("class S:\n    def run(self):\n        return 1\n")
    m, lock = pipeline(tmp_path, ["mod.py"])
    compiler = PythonStructuralPatchSetCompiler(project_root=tmp_path, workspace_path="a", project_key="a")
    duplicate = [PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("S", "run"), "function"), "    def run(self):\n        return 2")] * 2
    with pytest.raises(PythonStructuralPatchSetError):
        compiler.compile(repository_map=m, scope_lock=lock, requests=duplicate)
    overlap = [PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("S",), "class"), "class S:\n    pass"), PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("S", "run"), "function"), "    def run(self):\n        return 2")]
    with pytest.raises(PythonStructuralPatchSetError):
        compiler.compile(repository_map=m, scope_lock=lock, requests=overlap)


def test_structural_patch_set_rejects_empty(tmp_path):
    with pytest.raises(PythonStructuralPatchSetError):
        PythonStructuralPatchSetCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=RepositoryMapBuilder(project_root=tmp_path, workspace_path="a", project_key="a").build(), scope_lock=ScopeLockBuilder(project_root=tmp_path, workspace_path="a", project_key="a").build(repository_map=RepositoryMapBuilder(project_root=tmp_path, workspace_path="a", project_key="a").build(), allowed_write_paths=[]), requests=[])
