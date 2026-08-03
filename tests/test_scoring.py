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
async def test_general_prefers_gemini_initially(tmp_path):
    settings = Settings(
        gemini_api_key="x",
        github_token="x",
        groq_api_key="x",
        github_route_enabled=True,
    )
    store = OperationsStore(tmp_path / "ops.db")
    await store.initialize()
    quota = QuotaManager(settings=settings, store=store)
    breaker = CircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=300,
    )
    catalog = RouteCatalog(
        settings=settings,
        registry=FakeRegistry(),
    )
    scorer = ProviderScorer(
        catalog=catalog,
        quota=quota,
        circuit_breaker=breaker,
        store=store,
    )

    scores = await scorer.score_all(
        task_type="general",
        input_chars=100,
    )

    assert scores[0].route.key == "gemini"


@pytest.mark.asyncio
async def test_coding_prefers_github_initially(tmp_path):
    settings = Settings(
        gemini_api_key="x",
        github_token="x",
        groq_api_key="x",
        github_route_enabled=True,
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
        task_type="coding",
        input_chars=100,
    )

    assert scores[0].route.key == "github"
