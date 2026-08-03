from typing import Any

from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.tools.base import (
    BaseTool,
    ToolApprovalRequired,
    ToolError,
)
from app.tools.calculator import CalculatorTool
from app.tools.datetime_tool import CurrentDateTimeTool
from app.tools.git_tools import GitDiffTool, GitStatusTool
from app.tools.symbolic_math import SymbolicMathTool
from app.tools.terminal import SafeTerminalTool
from app.tools.text_stats import TextStatsTool
from app.tools.workspace_tools import (
    ProjectSummaryTool,
    WorkspaceListTool,
    WorkspaceReadTool,
    WorkspaceSearchTool,
    WorkspaceWriteTool,
)
from app.workspace.policy import WorkspacePolicy


class ToolRegistry:
    def __init__(self, approvals: ApprovalManager) -> None:
        self._tools: dict[str, BaseTool] = {}
        self.approvals = approvals

    def register(self, tool: BaseTool) -> None:
        normalized = tool.name.strip()
        if not normalized:
            raise ValueError("Araç adı boş olamaz.")
        if normalized in self._tools:
            raise ValueError(f"Araç zaten kayıtlı: {normalized}")
        self._tools[normalized] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def definitions(self, allowed_names: list[str] | set[str] | None = None) -> list[dict[str, Any]]:
        names = self.names()
        if allowed_names is not None:
            allowed = set(allowed_names)
            names = [name for name in names if name in allowed]
        return [self._tools[name].definition() for name in names]

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name.strip())
        if tool is None:
            raise ToolError(f"Bilinmeyen araç: {name}")
        return tool

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ToolError("Araç argümanları JSON nesnesi olmalıdır.")

        tool = self.get(name)
        if tool.requires_approval:
            preview = await tool.preview(arguments)

            if (
                tool.name == "workspace_write"
                and preview.get("changed") is False
            ):
                return {
                    "changed": False,
                    "no_op": True,
                    "path": preview.get("path"),
                    "bytes": preview.get("new_bytes", 0),
                    "backup": None,
                    "old_sha256": preview.get("old_sha256"),
                    "new_sha256": preview.get("new_sha256"),
                    "reason": "Dosya zaten hedef içerikle aynı.",
                }

            pending = await self.approvals.create(
                tool_name=tool.name,
                arguments=arguments,
                description=tool.approval_description,
                preview=preview,
            )
            raise ToolApprovalRequired(pending)

        return await tool.execute(arguments)

    async def execute_direct(
        self,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        """Execute a pre-authorized tool with a fresh preview.

        This bypasses only the user prompt. Tool validation, workspace
        confinement, stale-preview checks and command allowlists remain active.
        """
        arguments = arguments or {}
        tool = self.get(name)
        if not tool.requires_approval:
            return await tool.execute(arguments)
        preview = await tool.preview(arguments)
        if name == "workspace_write" and preview.get("changed") is False:
            return {
                "changed": False,
                "no_op": True,
                "path": preview.get("path"),
                "bytes": preview.get("new_bytes", 0),
                "backup": None,
                "old_sha256": preview.get("old_sha256"),
                "new_sha256": preview.get("new_sha256"),
                "reason": "Dosya zaten hedef içerikle aynı.",
            }
        checked = getattr(tool, "execute_approved_with_preview", None)
        if checked is not None:
            return await checked(arguments, preview=preview)
        return await tool.execute_approved(arguments)

    @staticmethod
    def is_high_risk(name: str, arguments: dict[str, Any]) -> bool:
        if name != "safe_terminal":
            return False
        return arguments.get("preset") in {
            "npm_install",
            "npm_install_dev",
            "install_node_lts",
            "pip_install_dev",
        }

    async def execute_approved(self, action_id: str) -> Any:
        # Consume before execution so a repeated/double click cannot run a
        # write or terminal command twice.
        action = await self.approvals.consume(action_id)
        tool = self.get(action.tool_name)
        if not tool.requires_approval:
            raise ToolError("Bu araç için onay akışı beklenmiyordu.")

        try:
            checked = getattr(
                tool,
                "execute_approved_with_preview",
                None,
            )
            if checked is not None:
                return await checked(
                    action.arguments,
                    preview=action.preview,
                )
            return await tool.execute_approved(action.arguments)
        except ToolError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or "ayrıntı vermeyen sistem hatası"
            raise ToolError(
                f"{tool.name} çalıştırılamadı "
                f"({type(exc).__name__}): {detail}"
            ) from exc

    async def reject_approval(self, action_id: str) -> dict[str, Any]:
        action = await self.approvals.reject(action_id)
        return {
            "rejected": True,
            "tool": action.tool_name,
            "message": "İşlem kullanıcı tarafından reddedildi.",
        }


def build_default_tool_registry(
    settings: Settings | None = None,
    approvals: ApprovalManager | None = None,
) -> ToolRegistry:
    settings = settings or Settings()
    approvals = approvals or ApprovalManager(
        ttl_seconds=settings.approval_ttl_seconds
    )
    workspace = WorkspacePolicy(
        root=settings.workspace_root,
        max_file_bytes=settings.workspace_max_file_bytes,
        max_search_results=settings.workspace_max_search_results,
    )

    registry = ToolRegistry(approvals)
    registry.register(CalculatorTool())
    registry.register(CurrentDateTimeTool())
    registry.register(TextStatsTool())
    registry.register(SymbolicMathTool())
    registry.register(ProjectSummaryTool(workspace))
    registry.register(WorkspaceListTool(workspace))
    registry.register(WorkspaceReadTool(workspace))
    registry.register(WorkspaceSearchTool(workspace))
    registry.register(WorkspaceWriteTool(workspace))
    registry.register(GitStatusTool(workspace))
    registry.register(GitDiffTool(workspace))
    registry.register(
        SafeTerminalTool(
            workspace=workspace,
            timeout_seconds=settings.command_timeout_seconds,
            max_output_chars=settings.command_output_max_chars,
        )
    )
    return registry
