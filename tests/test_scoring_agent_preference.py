from pathlib import Path
import pytest
from app.core.config import Settings
from app.orchestration.circuit_breaker import CircuitBreaker
from app.orchestration.quota import QuotaManager
from app.orchestration.routes import RouteCatalog
from app.orchestration.scoring import ProviderScorer
from app.providers.registry import ProviderRegistry
from app.storage.operations import OperationsStore
@pytest.mark.asyncio
async def test_preference_bonus(tmp_path:Path):
    settings=Settings(operations_database_path=tmp_path/'o.db',gemini_api_key='x',github_token='x',groq_api_key='x'); store=OperationsStore(settings.operations_database_path); await store.initialize(); registry=ProviderRegistry(settings)
    scorer=ProviderScorer(catalog=RouteCatalog(settings=settings,registry=registry),quota=QuotaManager(settings=settings,store=store),circuit_breaker=CircuitBreaker(failure_threshold=3,cooldown_seconds=30),store=store)
    scores=await scorer.score_all(task_type='coding',input_chars=1,preferred_routes=['gemini']); g=next(x for x in scores if x.route.key=='gemini'); assert any('Agent model tercihi' in r for r in g.reasons); await registry.close()
