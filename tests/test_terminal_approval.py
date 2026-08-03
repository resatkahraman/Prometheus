from pathlib import Path

import pytest

from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.tools.base import ToolApprovalRequired
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_terminal_requires_approval(tmp_path: Path):
    (tmp_path / "hello.py").write_text("print('ok')\n", encoding="utf-8")
    registry = build_default_tool_registry(
        settings=Settings(
            workspace_root=tmp_path,
            command_timeout_seconds=30,
        ),
        approvals=ApprovalManager(ttl_seconds=300),
    )

    with pytest.raises(ToolApprovalRequired) as captured:
        await registry.execute(
            "safe_terminal",
            {"preset": "python_compile"},
        )

    result = await registry.execute_approved(captured.value.pending.id)
    assert result["success"] is True
