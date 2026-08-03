from pathlib import Path

import pytest

from app.supervisor.models import SupervisorCommand
from app.supervisor.store import SupervisorCommandStore


@pytest.mark.asyncio
async def test_commands_survive_store_recreation(tmp_path: Path):
    database = tmp_path / "supervisor.db"
    first = SupervisorCommandStore(
        ttl_seconds=3600,
        max_events=100,
        database_path=database,
    )
    command = SupervisorCommand(
        id="cmd-persistent",
        goal="test",
        status="ready",
        autonomy_mode="task",
        plan_text="",
        tasks=[],
    )
    await first.put(command)

    second = SupervisorCommandStore(
        ttl_seconds=3600,
        max_events=100,
        database_path=database,
    )
    loaded = await second.get(command.id)
    assert loaded.id == command.id
    assert loaded.autonomy_mode == "task"
