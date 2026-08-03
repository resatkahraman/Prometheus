from pathlib import Path

from app.core.config import Settings
from app.tools.registry import build_default_tool_registry


def test_safe_terminal_has_install_presets(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    registry = build_default_tool_registry(settings=settings)
    tool = registry.get("safe_terminal")
    npm = tool._command({"preset": "npm_install"})
    pip = tool._command({"preset": "pip_install_dev"})
    assert npm == ["npm", "install"]
    assert "requirements-dev.txt" in pip
