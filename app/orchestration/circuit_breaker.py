import asyncio
import time
from dataclasses import dataclass


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    opened_until: float = 0.0


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_seconds: int,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, CircuitState] = {}
        self._lock = asyncio.Lock()

    async def can_call(self, provider: str) -> tuple[bool, int]:
        async with self._lock:
            state = self._states.setdefault(provider, CircuitState())
            now = time.time()

            if state.opened_until <= now:
                if state.opened_until:
                    state.opened_until = 0.0
                    state.consecutive_failures = 0
                return True, 0

            return False, max(1, int(state.opened_until - now))

    async def record_success(self, provider: str) -> None:
        async with self._lock:
            self._states[provider] = CircuitState()

    async def record_failure(
        self,
        provider: str,
        *,
        immediate: bool = False,
    ) -> None:
        async with self._lock:
            state = self._states.setdefault(provider, CircuitState())
            state.consecutive_failures += 1

            if immediate or state.consecutive_failures >= self.failure_threshold:
                state.opened_until = time.time() + self.cooldown_seconds

    async def status(self, provider: str) -> dict[str, int | bool]:
        async with self._lock:
            state = self._states.setdefault(provider, CircuitState())
            now = time.time()
            return {
                "open": state.opened_until > now,
                "retry_after_seconds": max(
                    0,
                    int(state.opened_until - now),
                ),
                "consecutive_failures": state.consecutive_failures,
            }
