from pathlib import Path

import pytest

from app.core.config import Settings
from app.tools.base import ToolError
from app.tools.registry import build_default_tool_registry


def test_targeted_dev_install_is_high_risk(tmp_path: Path):
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    assert registry.is_high_risk(
        "safe_terminal",
        {
            "preset": "npm_install_dev",
            "extra_args": ["@testing-library/jest-dom"],
        },
    )


def test_targeted_dev_install_command_is_argument_safe(
    monkeypatch,
    tmp_path: Path,
):
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    terminal = registry.get("safe_terminal")
    monkeypatch.setattr(terminal, "_resolve_npm_base", lambda: ["npm"])

    command, missing, logical = terminal._resolved_command(
        {
            "preset": "npm_install_dev",
            "extra_args": ["@testing-library/jest-dom"],
        }
    )
    assert missing is None
    assert command == [
        "npm", "install", "--save-dev", "@testing-library/jest-dom"
    ]
    assert logical == command

    with pytest.raises(ToolError):
        terminal._resolved_command(
            {
                "preset": "npm_install_dev",
                "extra_args": ["pkg && calc.exe"],
            }
        )
