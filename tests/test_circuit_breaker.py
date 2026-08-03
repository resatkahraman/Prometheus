import pytest

from app.orchestration.circuit_breaker import CircuitBreaker


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)

    await breaker.record_failure("gemini")
    allowed, _ = await breaker.can_call("gemini")
    assert allowed is True

    await breaker.record_failure("gemini")
    allowed, retry_after = await breaker.can_call("gemini")
    assert allowed is False
    assert retry_after > 0


@pytest.mark.asyncio
async def test_success_resets_circuit():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    await breaker.record_failure("github")
    await breaker.record_success("github")

    allowed, _ = await breaker.can_call("github")
    assert allowed is True
