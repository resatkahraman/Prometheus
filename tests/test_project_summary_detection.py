from pathlib import Path

import pytest

from app.tools.workspace_tools import ProjectSummaryTool
from app.workspace.policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_manifestless_python_project_is_detected(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "print('Adam')\n",
        encoding="utf-8",
    )
    workspace = WorkspacePolicy(
        root=tmp_path,
        max_file_bytes=100_000,
        max_search_results=20,
    )
    result = await ProjectSummaryTool(workspace).execute({})
    assert "python" in result["project_types"]
