import pytest

from app.storage.operations import OperationsStore


@pytest.mark.asyncio
async def test_cache_and_route_usage_round_trip(tmp_path):
    store = OperationsStore(tmp_path / "ops.db")
    await store.initialize()

    await store.set_cached("key", '{"answer":"ok"}', 60)
    assert await store.get_cached("key") == '{"answer":"ok"}'
    assert await store.cache_count() == 1

    assert await store.route_requests_today("gemini") == 0
    await store.increment_route_request("gemini")
    assert await store.route_requests_today("gemini") == 1

    await store.record_route_call(
        route_key="gemini",
        provider="gemini",
        model="gemini-3.1-flash-lite",
        success=True,
        latency_ms=100,
        input_tokens=10,
        output_tokens=20,
    )
    stats = await store.route_stats()
    assert stats[0]["total_calls"] == 1
    assert stats[0]["route_key"] == "gemini"
