import os
from pathlib import Path
import stat
import sys

from app.core.config import Settings
from app.tools.registry import build_default_tool_registry
from app.tools.terminal import TERMINAL_RUNTIME_REVISION


def test_npm_child_process_path_contains_node_directory(monkeypatch, tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    registry = build_default_tool_registry(settings=settings)
    tool = registry.get("safe_terminal")

    fake_node = tmp_path / ("node.exe" if os.name == "nt" else "node")
    fake_node.write_text("", encoding="utf-8")
    monkeypatch.setattr(tool, "_resolve_executable", lambda name: str(fake_node) if name == "node" else None)
    monkeypatch.setattr(tool, "_resolve_npm_base", lambda: [str(fake_node), str(tmp_path / "npm-cli.js")])

    env, entries = tool._execution_environment([str(fake_node), str(tmp_path / "npm-cli.js"), "install"])

    assert str(tmp_path) in entries
    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path)
    assert env["PROMETHEUS_TERMINAL_RUNTIME_REVISION"] == TERMINAL_RUNTIME_REVISION
    assert env["ADAM_TERMINAL_RUNTIME_REVISION"] == TERMINAL_RUNTIME_REVISION


def test_install_uses_longer_timeout(tmp_path: Path):
    registry = build_default_tool_registry(settings=Settings(workspace_root=tmp_path, command_timeout_seconds=30))
    tool = registry.get("safe_terminal")
    assert tool._timeout_for_preset("npm_install") >= 900


def test_node_test_strips_vitest_flags(tmp_path: Path):
    pkg = tmp_path / "package.json"
    pkg.write_text('{"scripts": {"test": "node --test"}}', encoding="utf-8")
    registry = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    tool = registry.get("safe_terminal")
    
    cmd, missing, logical = tool._resolved_command({"preset": "node_test", "extra_args": ["--run", "--reporter=verbose", "test.js"]})
    assert "--run" not in cmd
    assert "--reporter=verbose" not in cmd
    assert "test.js" in cmd



import pytest


@pytest.mark.asyncio
async def test_node_native_verification_is_workspace_confined(
    tmp_path: Path,
):
    source = tmp_path / "valid.js"
    source.write_text(
        'import test from "node:test";\n'
        'import assert from "node:assert/strict";\n'
        'test("works", () => assert.equal(2 + 2, 4));\n',
        encoding="utf-8",
    )
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    tool = registry.get("safe_terminal")

    test_result = await tool.execute_approved(
        {"preset": "node_test", "extra_args": ["valid.js"]}
    )
    check_result = await tool.execute_approved(
        {"preset": "node_check", "extra_args": ["valid.js"]}
    )

    assert test_result["success"] is True
    assert check_result["success"] is True
    with pytest.raises(Exception, match="Güvensiz"):
        await tool.preview(
            {"preset": "node_check", "extra_args": ["../outside.js"]}
        )


@pytest.mark.asyncio
async def test_file_exists_verification_accepts_nonempty_html_and_confines_path(
    tmp_path: Path,
):
    (tmp_path / "planet.html").write_text("<!doctype html>", encoding="utf-8")
    registry = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    tool = registry.get("safe_terminal")

    result = await tool.execute_approved(
        {"preset": "file_exists", "extra_args": ["planet.html"]}
    )

    assert result["success"] is True
    with pytest.raises(Exception, match="Güvensiz"):
        await tool.preview(
            {"preset": "file_exists", "extra_args": ["../outside.html"]}
        )


@pytest.mark.asyncio
async def test_npm_lifecycle_child_can_find_node(monkeypatch, tmp_path: Path):
    bin_dir = tmp_path / "toolchain"
    bin_dir.mkdir()
    if os.name == "nt":
        fake_node = bin_dir / "node.cmd"
        fake_node.write_text("@exit /b 0\r\n", encoding="utf-8")
        lifecycle_call = (
            "subprocess.run('node --version', shell=True, check=False)"
        )
    else:
        fake_node = bin_dir / "node"
        fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_node.chmod(fake_node.stat().st_mode | stat.S_IEXEC)
        lifecycle_call = (
            "subprocess.run(['node', '--version'], check=False)"
        )
    fake_npm = bin_dir / "fake_npm.py"
    fake_npm.write_text(
        "import subprocess\n"
        "raise SystemExit("
        f"{lifecycle_call}.returncode"
        ")\n",
        encoding="utf-8",
    )

    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path, command_timeout_seconds=30)
    )
    tool = registry.get("safe_terminal")
    monkeypatch.setattr(
        tool,
        "_resolve_executable",
        lambda name: str(fake_node) if name == "node" else None,
    )
    monkeypatch.setattr(
        tool,
        "_resolve_npm_base",
        lambda: [sys.executable, str(fake_npm)],
    )

    result = await tool.execute_approved(
        {"preset": "npm_install", "extra_args": []}
    )

    assert result["success"] is True, result.get("stderr")
    assert result["exit_code"] == 0
