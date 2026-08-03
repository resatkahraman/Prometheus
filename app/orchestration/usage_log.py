import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class UsageLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def write(self, event: dict[str, Any]) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }

        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False, default=str)
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
