import asyncio
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class PendingAction:
    id: str
    tool_name: str
    arguments: dict[str, Any]
    description: str
    preview: dict[str, Any]
    created_at: datetime
    expires_at: datetime

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "description": self.description,
            "preview": self.preview,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


class ApprovalManager:
    def __init__(self, ttl_seconds: int = 1_800) -> None:
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, PendingAction] = {}
        self._lock = asyncio.Lock()

    async def _cleanup(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            action_id
            for action_id, action in self._pending.items()
            if action.expires_at <= now
        ]
        for action_id in expired:
            self._pending.pop(action_id, None)

    async def create(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        description: str,
        preview: dict[str, Any],
    ) -> PendingAction:
        async with self._lock:
            await self._cleanup()
            now = datetime.now(timezone.utc)
            action = PendingAction(
                id=secrets.token_urlsafe(18),
                tool_name=tool_name,
                arguments=arguments,
                description=description,
                preview=preview,
                created_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )
            self._pending[action.id] = action
            return action

    async def get(self, action_id: str) -> PendingAction:
        async with self._lock:
            await self._cleanup()
            action = self._pending.get(action_id)
            if action is None:
                raise KeyError("Onay isteği bulunamadı veya süresi doldu.")
            return action

    async def consume(self, action_id: str) -> PendingAction:
        async with self._lock:
            await self._cleanup()
            action = self._pending.pop(action_id, None)
            if action is None:
                raise KeyError("Onay isteği bulunamadı veya süresi doldu.")
            return action

    async def reject(self, action_id: str) -> PendingAction:
        return await self.consume(action_id)

    async def list_pending(self) -> list[PendingAction]:
        async with self._lock:
            await self._cleanup()
            return sorted(
                self._pending.values(),
                key=lambda item: item.created_at,
            )
