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
async def test_general_knowledge_does_not_prefer_groq_fast(tmp_path):
    settings = Settings(
        _env_file=None,
        gemini_api_key="x",
        github_token="x",
        github_route_enabled=True,
        groq_api_key="x",
        local_model_enabled=True,
        free_only_mode=True,
        paid_models_enabled=False,
        monthly_paid_budget_usd=0.0,
        gemini_daily_request_budget=450,
        github_daily_request_budget=120,
        groq_fast_daily_request_budget=500,
        groq_strong_daily_request_budget=150,
        free_quota_conserve_ratio=0.10,
        free_quota_max_pressure_penalty=35.0,
        learned_router_mode="shadow",
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
        task_type="general",
        input_chars=100,
    )

    assert scores[0].route.key == "gemini"
    remote_scores = [item for item in scores if not item.route.local]
    assert remote_scores[-1].route.key == "groq_fast"
