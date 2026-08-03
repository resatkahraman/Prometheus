from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.schemas import OrchestrateRequest
from app.agents.registry import build_default_agent_registry
from app.orchestration.circuit_breaker import CircuitBreaker
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.quota import QuotaManager
from app.orchestration.routes import ModelRoute, RouteCatalog
from app.orchestration.scoring import ProviderScorer
from app.providers.base import ProviderResponse
from app.providers.registry import ProviderRegistry
from app.storage.operations import OperationsStore
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class AlwaysAvailableRegistry:
    def get_optional(self, _name):
        return object()


class CountingProvider:
    default_model = "free-model"

    def __init__(self):
        self.calls = 0

    async def generate(self, _request):
        self.calls += 1
        return ProviderResponse(
            provider="github",
            model="free-model",
            content="Ücretsiz sağlayıcıdan doğrulanabilir ve anlamlı cevap.",
            latency_ms=5,
            input_tokens=10,
            output_tokens=4,
        )


class CountingRegistry:
    def __init__(self):
        self.provider = CountingProvider()

    def names(self):
        return ["github"]

    def get_optional(self, name):
        return self.provider if name == "github" else None

    def get(self, name):
        if name != "github":
            raise ValueError(name)
        return self.provider


class BudgetExhaustedAgent:
    def __init__(self):
        self.calls = 0

    async def run(self, _request):
        self.calls += 1
        raise RuntimeError(
            "Misyon model çağrısı bütçesi tükendi. "
            "Çağrı: 24/24."
        )


@pytest.mark.asyncio
async def test_mission_budget_is_persistent_and_atomic(tmp_path: Path):
    store = OperationsStore(tmp_path / "operations.db")
    await store.initialize()

    first = await store.reserve_mission_call(
        usage_scope="mission-1",
        estimated_input_tokens=40,
        max_calls=2,
        max_estimated_input_tokens=100,
    )
    second = await store.reserve_mission_call(
        usage_scope="mission-1",
        estimated_input_tokens=40,
        max_calls=2,
        max_estimated_input_tokens=100,
    )
    blocked = await store.reserve_mission_call(
        usage_scope="mission-1",
        estimated_input_tokens=10,
        max_calls=2,
        max_estimated_input_tokens=100,
    )
    token_blocked = await store.reserve_mission_call(
        usage_scope="mission-2",
        estimated_input_tokens=101,
        max_calls=2,
        max_estimated_input_tokens=100,
    )

    assert first["allowed"] is True
    assert second["allowed"] is True
    assert blocked["allowed"] is False
    assert blocked["calls_used"] == 2
    assert blocked["estimated_input_tokens_used"] == 80
    assert token_blocked["allowed"] is False
    assert token_blocked["calls_used"] == 0

    await store.record_mission_tokens(
        usage_scope="mission-1",
        input_tokens=25,
        output_tokens=7,
    )
    usage = await store.mission_usage("mission-1")
    assert usage is not None
    assert usage["actual_input_tokens"] == 25
    assert usage["output_tokens"] == 7


def test_free_only_master_lock_blocks_future_paid_route():
    paid_route = ModelRoute(
        key="future_paid",
        provider="github",
        model="powerful-model",
        label="Future paid model",
        quality=10,
        speed=10,
        economy=1,
        paid=True,
    )
    locked = RouteCatalog(
        settings=Settings(
            free_only_mode=True,
            paid_models_enabled=True,
            monthly_paid_budget_usd=100,
        ),
        registry=AlwaysAvailableRegistry(),
    )
    unlocked = RouteCatalog(
        settings=Settings(
            free_only_mode=False,
            paid_models_enabled=True,
            monthly_paid_budget_usd=100,
        ),
        registry=AlwaysAvailableRegistry(),
    )

    assert locked.is_enabled(paid_route) is False
    assert "Free-only" in (locked.disabled_reason(paid_route) or "")
    assert unlocked.is_enabled(paid_route) is True


@pytest.mark.asyncio
async def test_low_daily_quota_moves_preferred_free_route_back(
    tmp_path: Path,
):
    settings = Settings(
        github_daily_request_budget=100,
        free_quota_conserve_ratio=0.10,
        free_quota_max_pressure_penalty=35,
    )
    store = OperationsStore(tmp_path / "operations.db")
    await store.initialize()
    for _ in range(96):
        await store.increment_route_request("github")
    scorer = ProviderScorer(
        catalog=RouteCatalog(
            settings=settings,
            registry=AlwaysAvailableRegistry(),
        ),
        quota=QuotaManager(settings=settings, store=store),
        circuit_breaker=CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=30,
        ),
        store=store,
    )

    scores = await scorer.score_all(
        task_type="coding",
        input_chars=100,
        preferred_routes=["github", "groq_strong"],
    )
    github = next(item for item in scores if item.route.key == "github")

    assert any(
        "Ücretsiz kota koruma cezası" in reason
        for reason in github.reasons
    )
    assert scores[0].route.key != "github"


@pytest.mark.asyncio
async def test_orchestrator_stops_scope_without_paid_fallback(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        github_token="free-key",
        github_route_enabled=True,
        github_daily_request_budget=120,
        local_model_enabled=False,
        free_only_mode=True,
        paid_models_enabled=False,
        monthly_paid_budget_usd=0.0,
        mission_budget_enabled=True,
        cache_enabled=False,
        mission_max_model_calls=1,
        mission_max_estimated_input_tokens=10_000,
        operations_database_path=tmp_path / "operations.db",
        usage_log_path=tmp_path / "usage.jsonl",
    )
    store = OperationsStore(settings.operations_database_path)
    await store.initialize()
    registry = CountingRegistry()
    orchestrator = Orchestrator(
        settings=settings,
        registry=registry,
        store=store,
    )
    request = OrchestrateRequest(
        message="Bu ücretsiz misyon çağrısını tamamla.",
        mode="direct",
        provider="github",
        usage_scope="mission-hard-limit",
    )

    first = await orchestrator.run(request)
    assert first.answer
    with pytest.raises(RuntimeError, match="ücretli rotaya geçmedi"):
        await orchestrator.run(request)
    assert registry.provider.calls == 1


@pytest.mark.asyncio
async def test_free_mode_caps_hidden_provider_retries():
    registry = ProviderRegistry(
        Settings(
            github_token="free-key",
            max_retries=3,
            free_only_mode=True,
            free_provider_max_retries=1,
        )
    )
    try:
        provider = registry.get("github")
        assert provider.max_retries == 1
    finally:
        await registry.close()


@pytest.mark.asyncio
async def test_supervisor_does_not_retry_exhausted_mission_without_change(
    tmp_path: Path,
):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
        supervisor_auto_review=False,
        supervisor_auto_evidence_reconcile=False,
    )
    tools = build_default_tool_registry(settings=settings)
    agent = BudgetExhaustedAgent()
    service = SupervisorService(
        settings=settings,
        agent=agent,
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="free mission",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["complete"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=[],
        status="ready",
    )
    command = SupervisorCommand(
        id="mission-budget",
        goal="stay free",
        status="ready",
        plan_text="",
        tasks=[task],
    )
    await service.store.put(command)

    first = await service.run_task(
        command_id=command.id,
        task_id=task.id,
        background=False,
    )
    second = await service.run_task(
        command_id=command.id,
        task_id=task.id,
        background=False,
    )

    assert first.tasks[0].recovery_reason == "mission_budget_exhausted"
    assert "ücretli rotaya geçmedi" in (
        first.tasks[0].blocked_reason or ""
    )
    assert second.tasks[0].recovery_reason == "mission_budget_exhausted"
    assert agent.calls == 1
    assert any(
        event.type == "resume_ignored_no_state_change"
        for event in second.events
    )
