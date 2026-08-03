from pathlib import Path

import pytest

from app.core.config import Settings
from app.orchestration.circuit_breaker import CircuitBreaker
from app.orchestration.quota import QuotaManager
from app.orchestration.routes import RouteCatalog
from app.orchestration.scoring import ProviderScorer
from app.storage.operations import OperationsStore


class FakeRegistry:
    def get_optional(self, name):
        return object()


@pytest.mark.asyncio
async def test_architect_primary_preference_can_beat_coding_default(tmp_path: Path):
    settings = Settings(
        gemini_api_key="x",
        github_token="x",
        groq_api_key="x",
    )
    store = OperationsStore(tmp_path / "ops.db")
    await store.initialize()
    scorer = ProviderScorer(
        catalog=RouteCatalog(
            settings=settings,
            registry=FakeRegistry(),
        ),
        quota=QuotaManager(settings=settings, store=store),
        circuit_breaker=CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=300,
        ),
        store=store,
    )

    scores = await scorer.score_all(
        task_type="reasoning",
        input_chars=500,
        preferred_routes=[
            "gemini",
            "groq_strong",
            "github",
            "groq_fast",
        ],
    )

    assert scores[0].route.key == "gemini"
    assert any(
        "Agent model tercihi (birincil rota)" in reason
        for reason in scores[0].reasons
    )
