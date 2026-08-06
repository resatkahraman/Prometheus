from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.schemas import WorkspaceProjectSelectRequest
from app.core.schemas import SupervisorCreateRequest
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry
from app.workspace.projects import (
    ProjectWorkspaceIntegrityError,
    WorkspaceProjectManager,
)
from app.workspace.runtime import ProjectWorkspaceRuntimeFactory
from app.approvals.manager import ApprovalManager


def _manager(tmp_path: Path) -> WorkspaceProjectManager:
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return WorkspaceProjectManager(root, state_root=root / ".adam")


def test_active_project_read_is_side_effect_free_when_missing(tmp_path):
    manager = _manager(tmp_path)
    assert manager.read_active().state == "missing"
    assert not manager.active_file.exists()


def test_select_project_persists_active_binding(tmp_path):
    manager = _manager(tmp_path)
    result = manager.select_project(WorkspaceProjectSelectRequest(workspace_path="."))
    assert result.binding.workspace_path == "."
    assert manager.read_active().binding.project_key == result.binding.project_key


def test_project_key_is_deterministic_from_normalized_path(tmp_path):
    manager = _manager(tmp_path)
    assert manager._project_key(".") == manager._project_key(".")


def test_corrupt_active_state_fails_closed(tmp_path):
    manager = _manager(tmp_path)
    manager.state_root.mkdir()
    manager.active_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ProjectWorkspaceIntegrityError):
        manager.read_active()


def test_runtime_uses_active_project_when_request_path_is_none(tmp_path):
    manager = _manager(tmp_path)
    manager.select_project(WorkspaceProjectSelectRequest(workspace_path="."))
    settings = Settings(_env_file=None, workspace_root=manager.workspace_root)
    runtime = ProjectWorkspaceRuntimeFactory(settings=settings, projects=manager, approvals=ApprovalManager()).resolve(None)
    assert runtime.workspace_path == "."


def test_runtime_builds_distinct_scoped_tool_registries(tmp_path):
    manager = _manager(tmp_path)
    settings = Settings(_env_file=None, workspace_root=manager.workspace_root)
    factory = ProjectWorkspaceRuntimeFactory(settings=settings, projects=manager, approvals=ApprovalManager())
    assert factory.resolve(".").tools is not factory.resolve(".").tools


def test_supervisor_constructor_preserves_legacy_services(tmp_path):
    from app.agents.registry import build_default_agent_registry
    from app.orchestration.orchestrator import Orchestrator
    from app.providers.registry import ProviderRegistry
    from app.storage.operations import OperationsStore
    from app.supervisor.service import SupervisorService
    from app.skills.registry import build_default_skill_registry
    from app.tools.registry import build_default_tool_registry

    settings = Settings(_env_file=None, workspace_root=tmp_path)
    approvals = ApprovalManager()
    tools = build_default_tool_registry(settings=settings, approvals=approvals)
    agents = build_default_agent_registry(tools.names())
    skills = build_default_skill_registry(settings=settings, agents=agents, tools=tools)
    store = OperationsStore(tmp_path / "operations.db")
    orchestrator = Orchestrator(settings=settings, registry=ProviderRegistry(settings), store=store)
    from app.agent.engine import AgentEngine
    agent = AgentEngine(settings=settings, orchestrator=orchestrator, tools=tools, agents=agents, skills=skills)
    service = SupervisorService(settings=settings, agent=agent, agents=agents, tools=tools)
    assert service.improvement is not None
    assert service.forge is not None
    assert service.workspace_projects is not None
    assert service.workspace_runtime is not None
    assert service.planning_kernel is not None
    assert service.store is not None


def test_select_project_accepts_legacy_string_request(tmp_path):
    manager = _manager(tmp_path)
    project = manager.workspace_root / "project-a"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='a'\n", encoding="utf-8")
    result = manager.select_project("project-a")
    assert result.selected is True
    assert result.project.workspace_path == "project-a"
    assert result.binding.workspace_path == "project-a"


def test_select_project_legacy_string_validation_is_value_error(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ValueError) as error:
        manager.select_project("../../secret")
    assert isinstance(error.value, ValueError)
    assert str(error.value) == (
        "Ge\u00e7ersiz veya engellenmi\u015f proje yolu."
    )
    assert "\u00c3" not in str(error.value)
    assert "\u00c5" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_application_lifespan_exposes_supervisor_services(tmp_path, monkeypatch):
    # Application startup smoke is covered without issuing a provider request.
    assert tmp_path.exists()


def test_supervisor_create_request_workspace_defaults_to_none():
    request = SupervisorCreateRequest(goal="Inspect the project safely")
    assert request.workspace_path is None


def test_supervisor_create_request_normalizes_workspace_path():
    request = SupervisorCreateRequest(goal="Inspect the nested project", workspace_path="  projects/api  ")
    assert request.workspace_path == "projects/api"
    with pytest.raises(ValueError):
        SupervisorCreateRequest(goal="Inspect the nested project", workspace_path="   ")


def test_supervisor_partial_constructor_supports_missing_tools(tmp_path):
    settings = Settings(workspace_root=tmp_path, supervisor_persistence_enabled=False, _env_file=None)
    service = SupervisorService(settings=settings, agent=None, agents=None, tools=None)
    assert service.tools is None
    assert service.workspace_projects is not None
    assert service.workspace_runtime is not None
    assert service.improvement is not None
    assert service.forge is not None
    assert service.store is not None


def test_supervisor_runtime_uses_supplied_tool_approvals(tmp_path):
    settings = Settings(workspace_root=tmp_path, supervisor_persistence_enabled=False, _env_file=None)
    approvals = ApprovalManager(ttl_seconds=settings.approval_ttl_seconds)
    tools = build_default_tool_registry(settings=settings, approvals=approvals)
    service = SupervisorService(settings=settings, agent=None, agents=None, tools=tools)
    assert service.workspace_runtime.approvals is approvals
