from abc import ABC, abstractmethod
from typing import Any

from app.approvals.manager import PendingAction
from app.core.exceptions import ToolError


class ToolApprovalRequired(ToolError):
    def __init__(self, pending: PendingAction) -> None:
        super().__init__("Bu araç kullanıcı onayı gerektiriyor.")
        self.pending = pending


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    risk_level: str = "read"
    requires_approval: bool = False
    approval_description: str = "Bu işlem çalışma alanını değiştirebilir."

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError

    async def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"arguments": arguments}

    async def execute_approved(self, arguments: dict[str, Any]) -> Any:
        return await self.execute(arguments)

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
        }
