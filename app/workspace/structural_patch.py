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

PYTHON_STRUCTURAL_PATCH_REVISION = "python-structural-patch-v1"


class PythonStructuralPatchError(ValueError):
    pass


class PythonStructuralPatchStaleError(PythonStructuralPatchError):
    pass


_KIND_NODES = {"function": ast.FunctionDef, "async_function": ast.AsyncFunctionDef, "class": ast.ClassDef}


@dataclass(frozen=True)
class PythonSymbolSelector:
    symbol_path: tuple[str, ...]
    symbol_kind: str

    def __post_init__(self) -> None:
        if not self.symbol_path or any(not part or part in {".", ".."} for part in self.symbol_path) or self.symbol_kind not in _KIND_NODES:
            raise PythonStructuralPatchError("Structural patch selector is invalid.")


@dataclass(frozen=True)
class PythonStructuralPatchRequest:
    path: str
    selector: PythonSymbolSelector
    replacement_source: str


@dataclass(frozen=True)
class PythonStructuralPatchSnapshot:
    revision: str
    workspace_path: str
    project_key: str
    path: str
    symbol_path: tuple[str, ...]
    symbol_kind: str
    start_line: int
    end_line: int
    base_sha256: str
    base_size_bytes: int
    replacement_span_sha256: str
    replacement_span_size_bytes: int
    output_sha256: str
    output_size_bytes: int
    safe_patch_plan_digest: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision, "workspace_path": self.workspace_path, "project_key": self.project_key,
            "path": self.path, "symbol_path": list(self.symbol_path), "symbol_kind": self.symbol_kind,
            "start_line": self.start_line, "end_line": self.end_line, "base_sha256": self.base_sha256,
            "base_size_bytes": self.base_size_bytes, "replacement_span_sha256": self.replacement_span_sha256,
            "replacement_span_size_bytes": self.replacement_span_size_bytes, "output_sha256": self.output_sha256,
            "output_size_bytes": self.output_size_bytes, "safe_patch_plan_digest": self.safe_patch_plan_digest,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class CompiledPythonStructuralPatch:
    snapshot: PythonStructuralPatchSnapshot
    plan: SafePatchPlan
    changes: tuple[PatchChangeRequest, ...]


def _digest(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _verify_repository_map(repository_map: RepositoryMapSnapshot) -> None:
    try:
        if repository_map.revision != REPOSITORY_MAP_REVISION or repository_map.entry_count != len(repository_map.entries):
            raise ValueError
        paths = [entry.path for entry in repository_map.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError
        payload = repository_map.to_dict()
        digest = payload.pop("digest", None)
        if _digest(payload) != digest:
            raise ValueError
    except Exception:
        raise PythonStructuralPatchError("Repository map integrity check failed.") from None


def _line_info(raw: bytes) -> tuple[str, list[int], list[bytes]]:
    if b"\r\n" in raw:
        remainder = raw.replace(b"\r\n", b"")
        if b"\n" in remainder or b"\r" in remainder:
            raise PythonStructuralPatchError("Structural patch source has mixed line endings.")
        ending = "\r\n"
    else:
        if b"\r" in raw:
            raise PythonStructuralPatchError("Structural patch source has invalid line endings.")
        ending = "\n" if b"\n" in raw else ""
    lines = raw.splitlines(keepends=True)
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset); offset += len(line)
    if not lines and raw:
        starts = [0]; lines = [raw]
    return ending, starts, lines


def _resolve_symbol(tree: ast.Module, selector: PythonSymbolSelector) -> ast.AST:
    body: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for index, component in enumerate(selector.symbol_path):
        candidates = [item for item in body if isinstance(item, tuple(_KIND_NODES.values())) and item.name == component]
        if not candidates:
            raise PythonStructuralPatchError("Structural patch symbol was not found.")
        if len(candidates) > 1:
            raise PythonStructuralPatchError("Structural patch symbol is ambiguous.")
        node = candidates[0]
        if index < len(selector.symbol_path) - 1:
            if not isinstance(node, ast.ClassDef):
                raise PythonStructuralPatchError("Structural patch symbol was not found.")
            body = node.body
    assert node is not None
    if not isinstance(node, _KIND_NODES[selector.symbol_kind]):
        raise PythonStructuralPatchError("Structural patch symbol kind does not match.")
    return node


class PythonStructuralPatchCompiler:
    def __init__(self, *, project_root: Path, workspace_path: str, project_key: str, max_file_bytes: int = 1_048_576, max_search_results: int = 1_000) -> None:
        root = Path(project_root).expanduser()
        if not root.exists() or not root.is_dir() or root.is_symlink() or not workspace_path or not project_key or max_file_bytes <= 0:
            raise PythonStructuralPatchError("Structural patch compiler construction is invalid.")
        self.project_root = root.resolve(); self.workspace_path = workspace_path; self.project_key = project_key
        self.max_file_bytes = max_file_bytes
        self.policy = WorkspacePolicy(root=self.project_root, max_file_bytes=max_file_bytes, max_search_results=max_search_results)

    @classmethod
    def from_runtime(cls, runtime, *, settings) -> "PythonStructuralPatchCompiler":
        return cls(project_root=runtime.project_root, workspace_path=runtime.workspace_path, project_key=runtime.project_key, max_file_bytes=settings.workspace_max_file_bytes, max_search_results=settings.workspace_max_search_results)

    def compile(self, *, repository_map: RepositoryMapSnapshot, scope_lock: ScopeLock, request: PythonStructuralPatchRequest) -> CompiledPythonStructuralPatch:
        _verify_repository_map(repository_map)
        if (repository_map.workspace_path, repository_map.project_key) != (self.workspace_path, self.project_key) or (scope_lock.snapshot.workspace_path, scope_lock.snapshot.project_key) != (self.workspace_path, self.project_key):
            raise PythonStructuralPatchError("Structural patch inputs do not match the bound project.")
        if repository_map.truncated or repository_map.depth_truncated:
            raise PythonStructuralPatchError("Structural patch target must be an existing Python repository file.")
        try:
            canonical = scope_lock.assert_write(request.path)
        except ScopeLockViolation:
            raise PythonStructuralPatchError("Structural patch target is outside the authorized scope.") from None
        entry = next((item for item in repository_map.entries if item.path == canonical), None)
        if entry is None or entry.suffix != ".py" or entry.role not in {"source", "test"}:
            raise PythonStructuralPatchError("Structural patch target must be an existing Python repository file.")
        try:
            target = self.policy.resolve(canonical, must_exist=True)
        except (ToolError, OSError, ValueError):
            raise PythonStructuralPatchError("Structural patch target must be an existing Python repository file.") from None
        if target.is_symlink() or not target.is_file():
            raise PythonStructuralPatchError("Structural patch target must be an existing Python repository file.")
        try:
            raw = target.read_bytes()
        except OSError:
            raise PythonStructuralPatchError("Structural patch source could not be read.") from None
        if len(raw) > self.max_file_bytes or raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
            raise PythonStructuralPatchError("Structural patch requires BOM-free UTF-8 Python source.")
        try:
            source = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise PythonStructuralPatchError("Structural patch requires BOM-free UTF-8 Python source.") from None
        ending, starts, lines = _line_info(raw)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            raise PythonStructuralPatchError("Structural patch target is not valid Python source.") from None
        node = _resolve_symbol(tree, request.selector)
        if not hasattr(node, "end_lineno") or node.end_lineno is None:
            raise PythonStructuralPatchError("Structural patch symbol span is unavailable.")
        start_line = min([node.lineno] + [decorator.lineno for decorator in getattr(node, "decorator_list", [])])
        end_line = node.end_lineno
        parent_body = tree.body
        # Locate the direct lexical parent body for same-line sibling checks.
        if len(request.selector.symbol_path) > 1:
            parent = _resolve_symbol(tree, PythonSymbolSelector(request.selector.symbol_path[:-1], "class"))
            parent_body = parent.body  # type: ignore[attr-defined]
        for sibling in parent_body:
            if sibling is node or not hasattr(sibling, "end_lineno"):
                continue
            if sibling.lineno <= end_line and sibling.end_lineno >= start_line:
                raise PythonStructuralPatchError("Structural patch target does not occupy an isolated source span.")
        if start_line < 1 or end_line > len(lines):
            raise PythonStructuralPatchError("Structural patch symbol span is unavailable.")
        start_offset = starts[start_line - 1]
        end_offset = starts[end_line - 1] + len(lines[end_line - 1])
        original_span = raw[start_offset:end_offset]
        replacement = request.replacement_source
        if not isinstance(replacement, str) or not replacement or "\x00" in replacement:
            raise PythonStructuralPatchError("Structural replacement is invalid.")
        replacement_norm = replacement.replace("\r\n", "\n").replace("\r", "\n")
        if "\r" in replacement_norm:
            raise PythonStructuralPatchError("Structural replacement has invalid line endings.")
        first_nonempty = next((line for line in replacement_norm.split("\n") if line.strip()), "")
        target_line = lines[start_line - 1]
        target_prefix_bytes = target_line[: len(target_line) - len(target_line.lstrip(b" \t"))]
        target_prefix = target_prefix_bytes.decode("ascii")
        replacement_prefix = first_nonempty[: len(first_nonempty) - len(first_nonempty.lstrip(" \t"))]
        if replacement_prefix != target_prefix:
            raise PythonStructuralPatchError("Structural replacement indentation does not match the target.")
        semantic = textwrap.dedent(replacement_norm)
        try:
            replacement_tree = ast.parse(semantic)
        except SyntaxError:
            raise PythonStructuralPatchError("Structural replacement is not valid Python source.") from None
        if len(replacement_tree.body) != 1 or not isinstance(replacement_tree.body[0], tuple(_KIND_NODES.values())):
            raise PythonStructuralPatchError("Structural replacement does not preserve symbol identity.")
        replacement_node = replacement_tree.body[0]
        if type(replacement_node) is not type(node) or replacement_node.name != node.name:
            raise PythonStructuralPatchError("Structural replacement does not preserve symbol identity.")
        replacement_body = replacement_norm.replace("\n", ending) if ending else replacement_norm.replace("\n", "")
        had_newline = original_span.endswith((b"\n", b"\r\n"))
        if had_newline and not replacement_body.endswith(ending):
            replacement_body += ending
        if not had_newline:
            replacement_body = replacement_body.rstrip("\r\n")
        replacement_bytes = replacement_body.encode("utf-8")
        output = raw[:start_offset] + replacement_bytes + raw[end_offset:]
        try:
            ast.parse(output.decode("utf-8"))
        except (UnicodeDecodeError, SyntaxError):
            raise PythonStructuralPatchError("Structural patch output is not valid Python source.") from None
        if output == raw:
            raise PythonStructuralPatchError("Structural replacement makes no change.")
        base_hash = _hash(raw); output_hash = _hash(output); span_hash = _hash(replacement_bytes)
        plan_builder = SafePatchPlanBuilder(project_root=self.project_root, workspace_path=self.workspace_path, project_key=self.project_key, max_file_bytes=self.max_file_bytes)
        change = PatchChangeRequest(canonical, "replace", output.decode("utf-8"))
        try:
            plan = plan_builder.build(repository_map=repository_map, scope_lock=scope_lock, changes=(change,))
        except Exception as exc:
            if isinstance(exc, PythonStructuralPatchError):
                raise
            raise PythonStructuralPatchError("Structural patch plan could not be created.") from None
        operation = plan.snapshot.operations[0]
        if operation.preimage_sha256 != base_hash or operation.preimage_size_bytes != len(raw) or operation.replacement_sha256 != output_hash or operation.replacement_size_bytes != len(output):
            raise PythonStructuralPatchStaleError("Structural patch source changed during compilation.")
        snapshot_payload: dict[str, object] = {
            "revision": PYTHON_STRUCTURAL_PATCH_REVISION, "workspace_path": self.workspace_path, "project_key": self.project_key,
            "path": canonical, "symbol_path": list(request.selector.symbol_path), "symbol_kind": request.selector.symbol_kind,
            "start_line": start_line, "end_line": end_line, "base_sha256": base_hash, "base_size_bytes": len(raw),
            "replacement_span_sha256": span_hash, "replacement_span_size_bytes": len(replacement_bytes),
            "output_sha256": output_hash, "output_size_bytes": len(output), "safe_patch_plan_digest": plan.snapshot.digest,
        }
        snapshot = PythonStructuralPatchSnapshot(**snapshot_payload, digest=_digest(snapshot_payload))
        return CompiledPythonStructuralPatch(snapshot=snapshot, plan=plan, changes=(change,))
