import asyncio
from pathlib import Path

import pytest

from app.tools.terminal import SafeTerminalTool
from app.workspace.policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_terminal_does_not_use_asyncio_subprocess(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    workspace = WorkspacePolicy(
        root=tmp_path,
        max_file_bytes=100_000,
        max_search_results=20,
    )
    tool = SafeTerminalTool(
        workspace=workspace,
        timeout_seconds=30,
        max_output_chars=10_000,
    )

    async def forbidden_async_subprocess(*args, **kwargs):
        raise AssertionError("asyncio subprocess kullanılmamalı")

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        forbidden_async_subprocess,
    )

    result = await tool.execute_approved(
        {"preset": "python_compile"}
    )
    assert result["success"] is True
    assert result["exit_code"] == 0
