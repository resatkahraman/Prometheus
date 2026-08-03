import pytest
from app.orchestration.smart_router import (
    SmartModelRouter,
    TaskComplexity,
)


def test_smart_router_routes_simple_tasks_to_local():
    router = SmartModelRouter()
    decision = router.classify_and_route("Fix a small typo in README.md")

    assert decision.complexity == TaskComplexity.LOCAL_LIGHT
    assert decision.target_route == "local_qwen"
    assert decision.preferred_routes[0] == "local_qwen"
    assert router.ledger.total_local_requests == 1
    assert router.ledger.estimated_savings_usd > 0.0


def test_smart_router_leaves_architecture_tasks_to_quality_scorer():
    router = SmartModelRouter()
    decision = router.classify_and_route("Refactor multi-file system architecture and database schema")

    assert decision.complexity == TaskComplexity.QUALITY_CRITICAL
    assert decision.target_route == "local_qwen"
    assert decision.preferred_routes == router.default_routes
    assert router.ledger.total_quality_routed_requests == 1


def test_smart_router_respects_explicit_exclusions():
    router = SmartModelRouter()
    decision = router.classify_and_route(
        "Fix a typo",
        excluded_routes=["local_qwen"],
    )

    assert "local_qwen" not in decision.preferred_routes
    assert decision.complexity == TaskComplexity.QUALITY_CRITICAL
