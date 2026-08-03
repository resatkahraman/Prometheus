from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
import re


_NUMBERED_LINE = re.compile(r"^\s*\d+:\s?")
_JS_IMPORT = re.compile(
    r"""(?:import[\s\S]*?\bfrom\s*|import\s*|require\s*\(\s*)"""
    r"""["']([^"']+)["']""",
)
_JS_NAMED_IMPORT = re.compile(
    r"""import\s*\{([^}]+)\}\s*from\s*["']([^"']+)["']""",
    re.MULTILINE,
)
_JS_SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?"
    r"(?:(async\s+)?function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_HTML_DEPENDENCY = re.compile(
    r"""<(?:script|link)\b[^>]*(?:src|href)=["']([^"']+)["']""",
    re.IGNORECASE,
)
_CSS_IMPORT = re.compile(r"""@import\s+(?:url\()?["']([^"']+)["']""")


@dataclass(frozen=True)
class IndexedSymbol:
    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class IndexedDependency:
    reference: str
    resolved_path: str | None
    kind: str


@dataclass(frozen=True)
class NamedImport:
    name: str
    reference: str
    resolved_path: str | None


def plain_text(content: str) -> str:
    return "\n".join(
        _NUMBERED_LINE.sub("", line)
        for line in content.splitlines()
    )


def _resolve_relative(source_path: str, reference: str) -> str | None:
    normalized = reference.replace("\\", "/").strip()
    if not normalized.startswith("."):
        return None
    source = PurePosixPath(source_path.replace("\\", "/"))
    combined = source.parent.joinpath(normalized)
    parts: list[str] = []
    for part in combined.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    resolved = PurePosixPath(*parts)
    if resolved.suffix:
        return resolved.as_posix()
    return resolved.with_suffix(".js").as_posix()


def _python_index(
    path: str,
    text: str,
) -> tuple[list[IndexedSymbol], list[IndexedDependency]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    symbols: list[IndexedSymbol] = []
    dependencies: list[IndexedDependency] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                IndexedSymbol(node.name, "function", int(node.lineno))
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                IndexedSymbol(node.name, "class", int(node.lineno))
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.append(
                    IndexedDependency(alias.name, None, "python_import")
                )
        elif isinstance(node, ast.ImportFrom):
            reference = "." * node.level + (node.module or "")
            resolved = None
            if node.level:
                relative = "./" * node.level + (node.module or "")
                resolved = _resolve_relative(
                    path,
                    relative.replace(".", "/"),
                )
                if resolved and resolved.endswith(".js"):
                    resolved = resolved[:-3] + ".py"
            dependencies.append(
                IndexedDependency(reference, resolved, "python_import")
            )
    return symbols, dependencies


def _javascript_index(
    path: str,
    text: str,
) -> tuple[list[IndexedSymbol], list[IndexedDependency]]:
    symbols: list[IndexedSymbol] = []
    for match in _JS_SYMBOL.finditer(text):
        declaration = match.group(0).casefold()
        kind = (
            "function"
            if "function" in declaration
            else "class"
            if "class" in declaration
            else "binding"
        )
        line = text.count("\n", 0, match.start()) + 1
        symbols.append(IndexedSymbol(match.group(2), kind, line))

    dependencies = [
        IndexedDependency(
            reference=match.group(1),
            resolved_path=_resolve_relative(path, match.group(1)),
            kind="javascript_import",
        )
        for match in _JS_IMPORT.finditer(text)
    ]
    return symbols, dependencies


def index_source(
    path: str,
    content: str,
) -> tuple[list[IndexedSymbol], list[IndexedDependency]]:
    text = plain_text(content)
    suffix = PurePosixPath(path.replace("\\", "/")).suffix.casefold()
    if suffix == ".py":
        return _python_index(path, text)
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return _javascript_index(path, text)
    if suffix in {".html", ".htm"}:
        dependencies = [
            IndexedDependency(
                reference=match.group(1),
                resolved_path=_resolve_relative(path, "./" + match.group(1))
                if not match.group(1).startswith(".")
                else _resolve_relative(path, match.group(1)),
                kind="html_asset",
            )
            for match in _HTML_DEPENDENCY.finditer(text)
            if not match.group(1).startswith(("http://", "https://", "//"))
        ]
        return [], dependencies
    if suffix in {".css", ".scss"}:
        dependencies = [
            IndexedDependency(
                reference=match.group(1),
                resolved_path=_resolve_relative(path, match.group(1)),
                kind="css_import",
            )
            for match in _CSS_IMPORT.finditer(text)
        ]
        return [], dependencies
    return [], []


def named_imports(path: str, content: str) -> list[NamedImport]:
    text = plain_text(content)
    imports: list[NamedImport] = []
    for match in _JS_NAMED_IMPORT.finditer(text):
        reference = match.group(2)
        resolved = _resolve_relative(path, reference)
        for raw_name in match.group(1).split(","):
            cleaned = raw_name.strip()
            if not cleaned:
                continue
            cleaned = re.sub(r"^type\s+", "", cleaned)
            original = re.split(r"\s+as\s+", cleaned, maxsplit=1)[0]
            if original:
                imports.append(
                    NamedImport(
                        name=original.strip(),
                        reference=reference,
                        resolved_path=resolved,
                    )
                )
    return imports
