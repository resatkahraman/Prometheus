from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.tools.registry import ToolRegistry, build_default_tool_registry
from .projects import WorkspaceProjectManager


@dataclass(frozen=True)
class ProjectWorkspaceRuntime:
    workspace_path: str
    project_key: str
    project_root: Path
    tools: ToolRegistry


class ProjectWorkspaceRuntimeFactory:
    def __init__(self, *, settings: Settings, projects: WorkspaceProjectManager, approvals: ApprovalManager) -> None:
        self.settings = settings
        self.projects = projects
        self.approvals = approvals

    def resolve(self, workspace_path: str | None) -> ProjectWorkspaceRuntime:
        selected = workspace_path
        if selected is None:
            active = self.projects.read_active()
            selected = active.binding.workspace_path if active.binding is not None else "."
        rel, root, summary = self.projects.resolve_project(selected)
        scoped_settings = self.settings.model_copy(update={"workspace_root": root})
        tools = build_default_tool_registry(settings=scoped_settings, approvals=self.approvals)
        return ProjectWorkspaceRuntime(workspace_path=rel, project_key=summary.project_key, project_root=root, tools=tools)

    def resolve_explicit(self, workspace_path: str) -> ProjectWorkspaceRuntime:
        return self.resolve(workspace_path)
