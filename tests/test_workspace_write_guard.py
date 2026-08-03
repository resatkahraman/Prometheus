from pathlib import Path

import pytest

from app.core.config import Settings
from app.tools.base import ToolApprovalRequired, ToolError
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_identical_write_is_noop_without_approval(tmp_path: Path):
    (tmp_path / "score.py").write_text("x = 1\n", encoding="utf-8")
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )

    result = await registry.execute(
        "workspace_write",
        {"path": "score.py", "content": "x = 1\n"},
    )

    assert result["changed"] is False
    assert result["no_op"] is True
    assert await registry.approvals.list_pending() == []


@pytest.mark.asyncio
async def test_stale_preview_is_rejected(tmp_path: Path):
    target = tmp_path / "score.py"
    target.write_text("x = 1\n", encoding="utf-8")
    registry = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )

    with pytest.raises(ToolApprovalRequired) as captured:
        await registry.execute(
            "workspace_write",
            {"path": "score.py", "content": "x = 2\n"},
        )

    target.write_text("x = 3\n", encoding="utf-8")

    with pytest.raises(ToolError, match="STALE_PREVIEW"):
        await registry.execute_approved(
            captured.value.pending.id
        )

    assert target.read_text(encoding="utf-8") == "x = 3\n"
