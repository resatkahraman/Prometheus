import asyncio
from typing import Any

from app.tools.base import BaseTool, ToolError
from app.workspace.policy import WorkspacePolicy


async def _run_git(
    workspace: WorkspacePolicy,
    arguments: list[str],
    *,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    if not (workspace.root / ".git").exists():
        raise ToolError("Workspace bir Git deposu değil.")

    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            *arguments,
            cwd=str(workspace.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolError("Git çalıştırılabilir dosyası bulunamadı.") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise ToolError("Git komutu zaman aşımına uğradı.") from exc

    return {
        "command": ["git", *arguments],
        "exit_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:30_000],
        "stderr": stderr.decode("utf-8", errors="replace")[:10_000],
    }


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Workspace Git deposunun kısa durumunu salt okunur biçimde verir."
    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return await _run_git(
            self.workspace,
            ["status", "--short", "--branch"],
        )


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = (
        "Git çalışma ağacındaki değişiklikleri veya staged diff'i salt okunur "
        "biçimde gösterir."
    )
    parameters = {
        "type": "object",
        "properties": {
            "staged": {"type": "boolean"},
            "path": {"type": "string"},
        },
        "additionalProperties": False,
    }

    def __init__(self, workspace: WorkspacePolicy) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict[str, Any]) -> Any:
        command = ["diff", "--no-ext-diff", "--unified=3"]
        if bool(arguments.get("staged", False)):
            command.append("--cached")

        path_value = arguments.get("path")
        if path_value is not None:
            if not isinstance(path_value, str) or not path_value.strip():
                raise ToolError("'path' dolu bir metin olmalıdır.")
            resolved = self.workspace.resolve(path_value)
            command.extend(["--", self.workspace.relative(resolved)])

        return await _run_git(self.workspace, command)
