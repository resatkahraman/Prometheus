from typing import Any

import pytest

from app.approvals.manager import ApprovalManager
from app.tools.base import BaseTool, ToolApprovalRequired, ToolError
from app.tools.registry import ToolRegistry


class BlankFailureTool(BaseTool):
    name = "blank_failure"
    description = "Test tool"
    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    requires_approval = True
    risk_level = "execute"

    async def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"ready": True}

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise ToolError("Approval required")

    async def execute_approved(self, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError()


@pytest.mark.asyncio
async def test_blank_runtime_error_becomes_meaningful_tool_error():
    registry = ToolRegistry(ApprovalManager(ttl_seconds=300))
    registry.register(BlankFailureTool())

    with pytest.raises(ToolApprovalRequired) as captured:
        await registry.execute("blank_failure", {})

    with pytest.raises(ToolError) as error:
        await registry.execute_approved(captured.value.pending.id)

    assert "NotImplementedError" in str(error.value)
    assert "ayrıntı vermeyen" in str(error.value)
