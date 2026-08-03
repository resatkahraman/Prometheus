import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_preflight_requests_npm_install_before_doomed_test(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest --run"}, "devDependencies": {"vitest": "latest"}}),
        encoding="utf-8",
    )
    registry = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    tool = registry.get("safe_terminal")
    monkeypatch.setattr(tool, "_resolve_npm_base", lambda: ["node", "npm-cli.js"])

    result = await tool.preflight({"preset": "npm_test", "extra_args": ["--run"]})

    assert result["ready"] is False
    assert result["failure_kind"] == "npm_dependencies_not_installed"
    assert result["remediation"]["arguments"]["preset"] == "npm_install"


@pytest.mark.asyncio
async def test_preflight_accepts_installed_vitest(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest --run"}}),
        encoding="utf-8",
    )
    binary = tmp_path / "node_modules" / ".bin" / "vitest"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    registry = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    tool = registry.get("safe_terminal")
    monkeypatch.setattr(tool, "_resolve_npm_base", lambda: ["node", "npm-cli.js"])

    result = await tool.preflight({"preset": "npm_test", "extra_args": ["--run"]})
    assert result["ready"] is True
