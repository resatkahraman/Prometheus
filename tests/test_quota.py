import pytest

from app.core.config import Settings
from app.orchestration.quota import QuotaManager
from app.storage.operations import OperationsStore


@pytest.mark.asyncio
async def test_route_quota_blocks_after_budget(tmp_path):
    settings = Settings(
        gemini_api_key="test",
        github_token="test",
        gemini_daily_request_budget=1,
    )
    store = OperationsStore(tmp_path / "ops.db")
    await store.initialize()
    manager = QuotaManager(settings=settings, store=store)

    first = await manager.reserve_route_call("gemini")
    assert first.allowed is True

    second = await manager.check_route("gemini")
    assert second.allowed is False
