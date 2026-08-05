from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import time

from app.supervisor.models import SupervisorCommand, utc_now


class SupervisorCommandStore:
    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_events: int,
        database_path: Path | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_events = max_events
        self.database_path = (
            database_path.expanduser().resolve()
            if database_path is not None
            else None
        )
        self._items: dict[str, tuple[float, SupervisorCommand]] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    @property
    def state_root(self) -> Path | None:
        if self.database_path is None:
            return None
        return self.database_path.parent

    def _initialize_sync(self) -> None:
        if self.database_path is None:
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS supervisor_commands (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_supervisor_updated "
                "ON supervisor_commands(updated_at DESC)"
            )
            connection.commit()

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._initialize_sync)
        self._initialized = True

    async def _cleanup_memory(self) -> None:
        now = time.monotonic()
        expired = [
            command_id
            for command_id, (created, _command) in self._items.items()
            if now - created > self.ttl_seconds
        ]
        for command_id in expired:
            self._items.pop(command_id, None)

    def _put_sync(self, command: SupervisorCommand) -> None:
        assert self.database_path is not None
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO supervisor_commands(id, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    command.id,
                    command.created_at,
                    command.updated_at,
                    command.model_dump_json(),
                ),
            )
            connection.commit()

    def _get_sync(self, command_id: str) -> SupervisorCommand | None:
        assert self.database_path is not None
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT payload FROM supervisor_commands WHERE id=?",
                (command_id,),
            ).fetchone()
        if row is None:
            return None
        return SupervisorCommand.model_validate_json(row[0])

    def _list_sync(self) -> list[SupervisorCommand]:
        assert self.database_path is not None
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT payload FROM supervisor_commands "
                "ORDER BY updated_at DESC"
            ).fetchall()
        return [SupervisorCommand.model_validate_json(row[0]) for row in rows]

    def _delete_sync(self, command_id: str) -> bool:
        assert self.database_path is not None
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "DELETE FROM supervisor_commands WHERE id=?",
                (command_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

    async def put(self, command: SupervisorCommand) -> None:
        async with self._lock:
            await self._ensure_initialized()
            command.updated_at = utc_now()
            if len(command.events) > self.max_events:
                command.events = command.events[-self.max_events :]
            if self.database_path is not None:
                try:
                    await asyncio.to_thread(self._put_sync, command)
                    return
                except sqlite3.OperationalError:
                    # Read-only packaged/test environments must not crash
                    # the Supervisor. Runtime falls back to memory while the
                    # normal writable workspace still uses SQLite.
                    self.database_path = None
                    self._initialized = True
            await self._cleanup_memory()
            created = self._items.get(
                command.id,
                (time.monotonic(), command),
            )[0]
            self._items[command.id] = (created, command)

    async def get(self, command_id: str) -> SupervisorCommand:
        async with self._lock:
            await self._ensure_initialized()
            if self.database_path is not None:
                try:
                    command = await asyncio.to_thread(
                        self._get_sync,
                        command_id,
                    )
                except sqlite3.OperationalError:
                    self.database_path = None
                    self._initialized = True
                else:
                    if command is None:
                        raise KeyError("Komut oturumu bulunamadı.")
                    return command
            await self._cleanup_memory()
            item = self._items.get(command_id)
            if item is None:
                raise KeyError(
                    "Komut oturumu bulunamadı veya süresi doldu."
                )
            return item[1]

    async def list(self) -> list[SupervisorCommand]:
        async with self._lock:
            await self._ensure_initialized()
            if self.database_path is not None:
                try:
                    return await asyncio.to_thread(self._list_sync)
                except sqlite3.OperationalError:
                    self.database_path = None
                    self._initialized = True
            await self._cleanup_memory()
            return [
                command
                for _created, command in sorted(
                    self._items.values(),
                    key=lambda item: item[1].created_at,
                    reverse=True,
                )
            ]

    async def delete(self, command_id: str) -> bool:
        async with self._lock:
            await self._ensure_initialized()
            if self.database_path is not None:
                try:
                    return await asyncio.to_thread(
                        self._delete_sync, command_id
                    )
                except sqlite3.OperationalError:
                    self.database_path = None
                    self._initialized = True
            await self._cleanup_memory()
            return self._items.pop(command_id, None) is not None
