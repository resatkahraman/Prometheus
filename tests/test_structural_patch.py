from pathlib import Path

import pytest

from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder
from app.workspace.structural_patch import (
    PythonStructuralPatchCompiler,
    PythonStructuralPatchError,
    PythonStructuralPatchRequest,
    PythonSymbolSelector,
)


def pipeline(root, path):
    m = RepositoryMapBuilder(project_root=root, workspace_path="a", project_key="a").build()
    lock = ScopeLockBuilder(project_root=root, workspace_path="a", project_key="a").build(repository_map=m, allowed_write_paths=[path])
    return m, lock


def test_structural_patch_module_function_preserves_unrelated_bytes(tmp_path):
    source = b"# head\ndef alpha():\n    return 1\n\ndef beta():\n    return 2\n# tail\n"
    (tmp_path / "mod.py").write_bytes(source)
    m, lock = pipeline(tmp_path, "mod.py")
    result = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("alpha",), "function"), "def alpha():\n    return 3"))
    assert result.plan.snapshot.operations[0].operation == "replace"
    assert b"def beta():\n    return 2" in result.changes[0].replacement_text.encode()
    assert result.snapshot.output_sha256.startswith("sha256:")


def test_structural_patch_class_method(tmp_path):
    (tmp_path / "mod.py").write_text("class Service:\n    def run(self):\n        return 1\n    def keep(self):\n        return 2\n")
    m, lock = pipeline(tmp_path, "mod.py")
    result = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("Service", "run"), "function"), "    def run(self):\n        return 3"))
    assert "def keep" in result.changes[0].replacement_text


def test_structural_patch_async_kind_and_identity(tmp_path):
    (tmp_path / "mod.py").write_text("async def run():\n    return 1\n")
    m, lock = pipeline(tmp_path, "mod.py")
    with pytest.raises(PythonStructuralPatchError):
        PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), "def run():\n    return 2"))


def test_structural_patch_decorators_are_replaced(tmp_path):
    (tmp_path / "mod.py").write_text("@old\ndef run():\n    return 1\n")
    m, lock = pipeline(tmp_path, "mod.py")
    result = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), "@new\ndef run():\n    return 2"))
    assert "@old" not in result.changes[0].replacement_text and "@new" in result.changes[0].replacement_text


def test_structural_patch_rejects_missing_and_ambiguous(tmp_path):
    (tmp_path / "mod.py").write_text("def run():\n    pass\ndef run():\n    pass\n")
    m, lock = pipeline(tmp_path, "mod.py")
    compiler = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a")
    with pytest.raises(PythonStructuralPatchError):
        compiler.compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), "def run():\n    pass"))


def test_structural_patch_rejects_function_local_symbol(tmp_path):
    (tmp_path / "mod.py").write_text("def outer():\n    def inner():\n        pass\n")
    m, lock = pipeline(tmp_path, "mod.py")
    with pytest.raises(PythonStructuralPatchError):
        PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("outer", "inner"), "function"), "    def inner():\n        return 2"))


def test_structural_patch_rejects_rename_and_multiple_definitions(tmp_path):
    (tmp_path / "mod.py").write_text("def run():\n    return 1\n")
    m, lock = pipeline(tmp_path, "mod.py")
    compiler = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a")
    for replacement in ("def start():\n    pass", "def run():\n    pass\ndef other():\n    pass"):
        with pytest.raises(PythonStructuralPatchError):
            compiler.compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), replacement))


def test_structural_patch_rejects_bom_invalid_utf8_and_mixed_endings(tmp_path):
    target = tmp_path / "mod.py"
    target.write_bytes(b"\xef\xbb\xbfdef run():\n    pass\n")
    m, lock = pipeline(tmp_path, "mod.py")
    compiler = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a")
    request = PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), "def run():\n    pass")
    with pytest.raises(PythonStructuralPatchError):
        compiler.compile(repository_map=m, scope_lock=lock, request=request)


def test_structural_patch_crlf_preserved(tmp_path):
    (tmp_path / "mod.py").write_bytes(b"def run():\r\n    return 1\r\n")
    m, lock = pipeline(tmp_path, "mod.py")
    result = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), "def run():\n    return 2"))
    assert "\r\n" in result.changes[0].replacement_text and "\n" not in result.changes[0].replacement_text.replace("\r\n", "")


def test_structural_patch_snapshot_contains_no_source_content(tmp_path):
    marker = "UNIQUE_STRUCTURAL_MARKER"
    (tmp_path / "mod.py").write_text(f"def run():\n    return '{marker}'\n")
    m, lock = pipeline(tmp_path, "mod.py")
    result = PythonStructuralPatchCompiler(project_root=tmp_path, workspace_path="a", project_key="a").compile(repository_map=m, scope_lock=lock, request=PythonStructuralPatchRequest("mod.py", PythonSymbolSelector(("run",), "function"), "def run():\n    return 9"))
    assert marker not in str(result.snapshot.to_dict()) and str(tmp_path) not in str(result.snapshot.to_dict())
