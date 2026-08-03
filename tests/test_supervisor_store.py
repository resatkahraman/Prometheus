import pytest

from app.supervisor.models import SupervisorCommand
from app.supervisor.store import SupervisorCommandStore


@pytest.mark.asyncio
async def test_command_store_put_get():
    store = SupervisorCommandStore(
        ttl_seconds=3600,
        max_events=10,
    )
    command = SupervisorCommand(
        id="cmd",
        goal="test",
        status="planning",
        plan_text="",
        tasks=[],
    )
    await store.put(command)
    loaded = await store.get("cmd")
    assert loaded.goal == "test"
