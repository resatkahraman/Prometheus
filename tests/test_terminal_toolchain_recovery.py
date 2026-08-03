from pathlib import Path

import pytest

from app.tools.terminal import SafeTerminalTool
from app.workspace.policy import WorkspacePolicy


def make_tool(tmp_path: Path) -> SafeTerminalTool:
    return SafeTerminalTool(
        workspace=WorkspacePolicy(
            root=tmp_path,
            max_file_bytes=100_000,
            max_search_results=20,
        ),
        timeout_seconds=30,
        max_output_chars=10_000,
    )


@pytest.mark.asyncio
async def test_missing_npm_returns_structured_result(
    monkeypatch,
    tmp_path: Path,
):
    tool = make_tool(tmp_path)
    monkeypatch.setattr(tool, "_resolve_npm_base", lambda: None)

    result = await tool.execute_approved(
        {"preset": "npm_test", "extra_args": ["--run"]}
    )

    assert result["success"] is False
    assert result["failure_kind"] == "missing_command"
    assert result["missing_command"] == "npm"
    assert result["exit_code"] == 127
    assert result["remediation"]["arguments"]["preset"] == (
        "install_node_lts"
    )


@pytest.mark.asyncio
async def test_missing_npm_preview_does_not_raise(
    monkeypatch,
    tmp_path: Path,
):
    tool = make_tool(tmp_path)
    monkeypatch.setattr(tool, "_resolve_npm_base", lambda: None)

    preview = await tool.preview(
        {"preset": "npm_test", "extra_args": ["--run"]}
    )

    assert preview["available"] is False
    assert preview["missing_command"] == "npm"
    assert preview["logical_command"] == [
        "npm",
        "test",
        "--",
        "--run",
    ]
