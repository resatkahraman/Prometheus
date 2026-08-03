"""Low-cost routing advice layered on top of the evidence-based scorer.

The main scorer remains authoritative because it knows live quotas, circuit
breaker state, latency and verified task history. This advisor only adjusts
route preference order for short, low-risk work; it never forces a disabled
provider or bypasses the scorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class TaskComplexity(str, Enum):
    LOCAL_LIGHT = "local_light"
    QUALITY_CRITICAL = "quality_critical"


@dataclass(frozen=True)
class RouteDecision:
    complexity: TaskComplexity
    preferred_routes: tuple[str, ...]
    target_route: str | None
    estimated_cost_usd: float
    reason: str


@dataclass
class CostLedger:
    total_local_requests: int = 0
    total_quality_routed_requests: int = 0
    estimated_savings_usd: float = 0.0

    def record_routing(
        self,
        decision: RouteDecision,
        estimated_tokens: int = 500,
    ) -> None:
        if decision.complexity == TaskComplexity.LOCAL_LIGHT:
            self.total_local_requests += 1
            self.estimated_savings_usd += (
                estimated_tokens / 1000.0
            ) * 0.002
        else:
            self.total_quality_routed_requests += 1


class SmartModelRouter:
    """Provide conservative, scorer-compatible route preferences."""

    ARCHITECT_KEYWORDS = (
        "mimari",
        "architecture",
        "refactor",
        "system design",
        "multi-file",
        "çoklu dosya",
        "database schema",
        "veritabanı",
        "security audit",
        "güvenlik denetimi",
        "3d",
        "three.js",
        "webgl",
        "canvas animation",
        "animasyon",
        "interactive visualization",
        "etkileşimli görsel",
    )

    def __init__(
        self,
        default_routes: Iterable[str] = (
            "local_qwen",
            "local_expert",
            "gemini",
            "github",
            "groq_strong",
            "groq_fast",
        ),
    ) -> None:
        self.default_routes = tuple(dict.fromkeys(default_routes))
        self.ledger = CostLedger()

    def classify_and_route(
        self,
        goal: str,
        *,
        preferred_routes: Iterable[str] | None = None,
        excluded_routes: Iterable[str] | None = None,
        prefer_local: bool = True,
        estimated_tokens: int = 500,
    ) -> RouteDecision:
        normalized = goal.casefold()
        is_quality_critical = (
            len(goal) > 6_000
            or any(
                keyword.casefold() in normalized
                for keyword in self.ARCHITECT_KEYWORDS
            )
        )
        excluded = set(excluded_routes or ())
        base_routes = list(
            dict.fromkeys(preferred_routes or self.default_routes)
        )
        base_routes = [route for route in base_routes if route not in excluded]

        if (
            not is_quality_critical
            and prefer_local
            and "local_qwen" not in excluded
        ):
            routes = [
                "local_qwen",
                *(route for route in base_routes if route != "local_qwen"),
            ]
            complexity = TaskComplexity.LOCAL_LIGHT
            reason = (
                "Kısa ve düşük riskli görev: canlı puanlayıcıya yerel model "
                "ilk tercih olarak önerildi."
            )
        else:
            # Even quality-critical work starts with the fast 4B controller.
            # The 9B expert remains the immediate local fallback, avoiding a
            # 40-60 second cold load on every complex-looking request.
            routes = base_routes
            complexity = TaskComplexity.QUALITY_CRITICAL
            reason = (
                "Karmaşık veya uzun görev: canlı kalite, kota ve güvenilirlik "
                "puanları korunarak zorunlu yerel yönlendirme yapılmadı."
            )

        decision = RouteDecision(
            complexity=complexity,
            preferred_routes=tuple(routes),
            target_route=routes[0] if routes else None,
            estimated_cost_usd=0.0,
            reason=reason,
        )
        self.ledger.record_routing(decision, estimated_tokens=estimated_tokens)
        return decision
