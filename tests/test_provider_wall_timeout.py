from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time

import pytest

from app.core.config import Settings
from app.core.schemas import OrchestrateRequest
from app.orchestration.orchestrator import Orchestrator
from app.providers.base import ProviderResponse
from app.storage.operations import OperationsStore


class SlowProvider:
    async def generate(self, _request):
        await asyncio.sleep(5)
        return ProviderResponse(
            provider="github",
            model="slow-free-model",
            content="Bu cevap timeout'tan önce gelmemeli.",
            latency_ms=5_000,
        )


class SlowRegistry:
    def __init__(self) -> None:
        self.provider = SlowProvider()

    def get_optional(self, name: str):
        return self.provider if name == "github" else None

    def names(self) -> list[str]:
        return ["github"]

    def get(self, name: str):
        if name != "github":
            raise ValueError(name)
        return self.provider


@pytest.mark.asyncio
async def test_provider_wall_timeout_is_logged_and_releases_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(
        _env_file=None,
        github_token="test-token",
        gemini_api_key=None,
        groq_api_key=None,
        cache_enabled=False,
        operations_database_path=tmp_path / "operations.db",
        usage_log_path=tmp_path / "usage.jsonl",
        mission_max_model_calls=3,
        mission_max_estimated_input_tokens=10_000,
    )
    store = OperationsStore(settings.operations_database_path)
    await store.initialize()
    orchestrator = Orchestrator(
        settings=settings,
        registry=SlowRegistry(),
        store=store,
    )
    monkeypatch.setattr(
        orchestrator,
        "_provider_wall_timeout",
        lambda _request: 0.02,
    )

    started = time.perf_counter()
    with pytest.raises(RuntimeError, match="toplam yanıt süresi"):
        await orchestrator.run(
            OrchestrateRequest(
                message="Kısa bir kod cevabı üret.",
                mode="direct",
                provider="github",
                usage_scope="wall-timeout-mission",
            )
        )
    elapsed = time.perf_counter() - started

    assert elapsed < 1
    usage = await store.mission_usage("wall-timeout-mission")
    assert usage is not None
    assert usage["reserved_calls"] == 1
    records = [
        json.loads(line)
        for line in settings.usage_log_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert len(records) == 1
    assert records[0]["success"] is False
    assert "fallback rotasına geçiliyor" in records[0]["error"]


def test_adaptive_provider_wall_timeout_gives_large_outputs_more_time(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        github_token="test-token",
        gemini_api_key=None,
        groq_api_key=None,
        operations_database_path=tmp_path / "operations.db",
        usage_log_path=tmp_path / "usage.jsonl",
        provider_call_wall_timeout_seconds=90,
    )
    orchestrator = Orchestrator(
        settings=settings,
        registry=SlowRegistry(),
        store=OperationsStore(settings.operations_database_path),
    )
    short = type("Request", (), {"max_output_tokens": 1_000})()
    large = type("Request", (), {"max_output_tokens": 12_000})()

    assert orchestrator._provider_wall_timeout(short) < 30
    assert orchestrator._provider_wall_timeout(large) == 90
