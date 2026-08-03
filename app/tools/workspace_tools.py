import difflib
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolError
from app.workspace.policy import WorkspacePolicy


class WorkspaceListTool(BaseTool):
    name = "workspace_list"
    description = (
        "Workspace içindeki dosya ve klasörleri listeler. "
        "Kod tabanını tanımak için ilk kullanılabilecek araçtır."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative klasör; varsayılan kök.",
            },
            "depth": {
                "type": "integer",
                "minimum": 1,
                "maximum": 6,
                "description": "En fazla klasör derinliği.",
            },
            "max_entries": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
            },
        },
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict[str, Any]) -> Any:
        start = self.workspace.resolve(
            arguments.get("path", "."),
            must_exist=True,
        )
        depth = int(arguments.get("depth", 3))
        max_entries = int(arguments.get("max_entries", 200))
        depth = min(max(depth, 1), 6)
        max_entries = min(max(max_entries, 1), 500)

        if start.is_file():
            return {
                "root": self.workspace.relative(start),
                "entries": [
                    {
                        "path": self.workspace.relative(start),
                        "type": "file",
                        "size": start.stat().st_size,
                    }
                ],
                "truncated": False,
            }

        base_depth = len(start.relative_to(self.workspace.root).parts)
        entries: list[dict[str, Any]] = []

        for path in sorted(start.rglob("*"), key=lambda item: item.as_posix()):
            relative_parts = path.relative_to(self.workspace.root).parts
            if len(relative_parts) - base_depth > depth:
                continue
            try:
                resolved = self.workspace.resolve(
                    path.relative_to(self.workspace.root)
                )
            except ToolError:
                continue
            if resolved.is_symlink():
                continue

            entries.append(
                {
                    "path": self.workspace.relative(resolved),
                    "type": "directory" if resolved.is_dir() else "file",
                    "size": resolved.stat().st_size if resolved.is_file() else None,
                }
            )
            if len(entries) >= max_entries:
                return {
                    "root": self.workspace.relative(start),
                    "entries": entries,
                    "truncated": True,
                }

        return {
            "root": self.workspace.relative(start),
            "entries": entries,
            "truncated": False,
        }


class WorkspaceReadTool(BaseTool):
    name = "workspace_read"
    description = (
        "Workspace içindeki UTF-8 metin dosyasını satır numaralarıyla okur."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict[str, Any]) -> Any:
        path_value = arguments.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ToolError("'path' zorunludur.")

        path = self.workspace.resolve(path_value, must_exist=True)
        self.workspace.ensure_text_file(path)

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError("Dosya UTF-8 metin olarak okunamadı.") from exc

        lines = text.splitlines()
        start_line = int(arguments.get("start_line", 1))
        end_line = int(arguments.get("end_line", min(len(lines), start_line + 299)))
        start_line = max(1, start_line)
        end_line = min(max(start_line, end_line), len(lines))
        selected = lines[start_line - 1 : end_line]

        return {
            "path": self.workspace.relative(path),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": len(lines),
            "content": "\n".join(
                f"{line_number:>5}: {line}"
                for line_number, line in enumerate(selected, start=start_line)
            ),
            "truncated": end_line < len(lines),
        }


class WorkspaceSearchTool(BaseTool):
    name = "workspace_search"
    description = (
        "Workspace dosyalarında metin veya düzenli ifade arar ve eşleşen "
        "satırları döndürür."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "regex": {"type": "boolean"},
            "case_sensitive": {"type": "boolean"},
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict[str, Any]) -> Any:
        query = arguments.get("query")
        if not isinstance(query, str) or not query:
            raise ToolError("'query' dolu metin olmalıdır.")
        if len(query) > 500:
            raise ToolError("Arama sorgusu çok uzun.")

        start = self.workspace.resolve(
            arguments.get("path", "."),
            must_exist=True,
        )
        use_regex = bool(arguments.get("regex", False))
        case_sensitive = bool(arguments.get("case_sensitive", False))
        max_results = min(
            int(
                arguments.get(
                    "max_results",
                    self.workspace.max_search_results,
                )
            ),
            self.workspace.max_search_results,
        )

        flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            try:
                matcher = re.compile(query, flags)
            except re.error as exc:
                raise ToolError(f"Geçersiz regex: {exc}") from exc
        else:
            matcher = re.compile(re.escape(query), flags)

        results: list[dict[str, Any]] = []
        scanned_files = 0

        for file_path in self.workspace.iter_files(start):
            scanned_files += 1
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue

            for line_number, line in enumerate(lines, start=1):
                if matcher.search(line):
                    results.append(
                        {
                            "path": self.workspace.relative(file_path),
                            "line": line_number,
                            "preview": line.strip()[:500],
                        }
                    )
                    if len(results) >= max_results:
                        return {
                            "query": query,
                            "results": results,
                            "scanned_files": scanned_files,
                            "truncated": True,
                        }

        return {
            "query": query,
            "results": results,
            "scanned_files": scanned_files,
            "truncated": False,
        }


class ProjectSummaryTool(BaseTool):
    name = "project_summary"
    description = (
        "Workspace proje türünü, önemli manifestleri ve üst düzey yapıyı "
        "hızlıca özetler."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict[str, Any]) -> Any:
        root = self.workspace.root
        markers = {
            "python": ["pyproject.toml", "requirements.txt", "setup.py"],
            "node": ["package.json"],
            "flutter": ["pubspec.yaml"],
            "android_gradle": ["build.gradle", "build.gradle.kts", "settings.gradle"],
            "rust": ["Cargo.toml"],
            "dotnet": [],
        }

        detected: list[str] = []
        manifests: list[str] = []
        for project_type, filenames in markers.items():
            for filename in filenames:
                if (root / filename).exists():
                    detected.append(project_type)
                    manifests.append(filename)
                    break

        if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
            detected.append("dotnet")
            manifests.extend(
                [path.name for path in root.glob("*.sln")]
                + [path.name for path in root.glob("*.csproj")]
            )

        # Small test projects may contain source files without a manifest.
        if "python" not in detected:
            try:
                next(root.rglob("*.py"))
                detected.append("python")
            except StopIteration:
                pass

        top_level = []
        for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            try:
                resolved = self.workspace.resolve(path.relative_to(root))
            except ToolError:
                continue
            top_level.append(
                {
                    "name": resolved.name,
                    "type": "directory" if resolved.is_dir() else "file",
                }
            )
            if len(top_level) >= 100:
                break

        return {
            "workspace_root": str(root),
            "project_types": sorted(set(detected)) or ["unknown"],
            "manifests": sorted(set(manifests)),
            "git_repository": (root / ".git").exists(),
            "top_level": top_level,
        }


class WorkspaceWriteTool(BaseTool):
    name = "workspace_write"
    description = (
        "Bir workspace dosyasını oluşturur veya tüm içeriğini değiştirir. "
        "Gerçek yazma öncesinde kullanıcıya unified diff gösterir ve onay ister."
    )
    risk_level = "write"
    requires_approval = True
    approval_description = (
        "Dosya oluşturma/değiştirme işlemi çalışma alanını değiştirecek."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    def _validate(self, arguments: dict[str, Any]) -> tuple[Path, str]:
        path_value = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ToolError("'path' zorunludur.")
        if not isinstance(content, str):
            raise ToolError("'content' metin olmalıdır.")
        encoded_size = len(content.encode("utf-8"))
        if encoded_size > self.workspace.max_file_bytes:
            raise ToolError(
                f"Yeni içerik {encoded_size} bayt ile dosya sınırını aşıyor."
            )
        path = self.workspace.resolve(path_value, for_write=True)
        if path.exists() and path.is_dir():
            raise ToolError("Bir klasör dosya olarak değiştirilemez.")
        return path, content

    async def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path, content = self._validate(arguments)
        old_content = ""
        exists = path.exists()
        if exists:
            self.workspace.ensure_text_file(path)
            old_content = path.read_text(encoding="utf-8")

        diff_lines = list(
            difflib.unified_diff(
                old_content.splitlines(),
                content.splitlines(),
                fromfile=f"a/{self.workspace.relative(path)}",
                tofile=f"b/{self.workspace.relative(path)}",
                lineterm="",
            )
        )
        diff = "\n".join(diff_lines)
        if len(diff) > 20_000:
            diff = diff[:20_000] + "\n... diff kırpıldı ..."

        old_bytes = old_content.encode("utf-8")
        new_bytes = content.encode("utf-8")
        return {
            "path": self.workspace.relative(path),
            "operation": "update" if exists else "create",
            "old_bytes": len(old_bytes),
            "new_bytes": len(new_bytes),
            "old_sha256": hashlib.sha256(old_bytes).hexdigest(),
            "new_sha256": hashlib.sha256(new_bytes).hexdigest(),
            "changed": old_content != content,
            "diff": diff,
        }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise ToolError("workspace_write yalnızca onaylı akışta çalışabilir.")

    async def execute_approved(
        self,
        arguments: dict[str, Any],
    ) -> Any:
        return await self.execute_approved_with_preview(
            arguments,
            preview=None,
        )

    async def execute_approved_with_preview(
        self,
        arguments: dict[str, Any],
        *,
        preview: dict[str, Any] | None,
    ) -> Any:
        path, content = self._validate(arguments)
        path.parent.mkdir(parents=True, exist_ok=True)

        current_content = ""
        if path.exists():
            self.workspace.ensure_text_file(path)
            current_content = path.read_text(encoding="utf-8")

        current_bytes = current_content.encode("utf-8")
        target_bytes = content.encode("utf-8")
        current_sha = hashlib.sha256(current_bytes).hexdigest()
        target_sha = hashlib.sha256(target_bytes).hexdigest()

        if preview is not None:
            expected_old_sha = preview.get("old_sha256")
            if (
                isinstance(expected_old_sha, str)
                and expected_old_sha
                and current_sha != expected_old_sha
            ):
                raise ToolError(
                    "STALE_PREVIEW: Dosya onay önizlemesinden sonra "
                    "değişti. Eski diff uygulanmadı; güncel dosya yeniden "
                    "okunarak yeni önizleme oluşturulmalıdır."
                )

        if current_sha == target_sha:
            return {
                "changed": False,
                "no_op": True,
                "path": self.workspace.relative(path),
                "bytes": len(target_bytes),
                "backup": None,
                "old_sha256": current_sha,
                "new_sha256": target_sha,
                "reason": "Dosya zaten hedef içerikle aynı.",
            }

        backup_relative: str | None = None
        if path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = (
                self.workspace.root
                / ".adam"
                / "backups"
                / stamp
                / path.relative_to(self.workspace.root)
            )
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(path.read_bytes())
            backup_relative = (
                backup.relative_to(self.workspace.root).as_posix()
            )

        temp_fd, temp_name = tempfile.mkstemp(
            prefix=".adam-write-",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(
                temp_fd,
                "w",
                encoding="utf-8",
                newline="",
            ) as handle:
                handle.write(content)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        return {
            "changed": True,
            "no_op": False,
            "path": self.workspace.relative(path),
            "bytes": len(target_bytes),
            "backup": backup_relative,
            "old_sha256": current_sha,
            "new_sha256": target_sha,
        }
