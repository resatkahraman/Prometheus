from app.core.config import Settings
from app.tools.registry import build_default_tool_registry
from app.agents.registry import build_default_agent_registry


def test_backend_can_write_requirements_dev(tmp_path):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    registry = build_default_agent_registry(tools.names())
    backend = registry.get("backend")
    assert "requirements-dev.txt" in backend.write_paths
