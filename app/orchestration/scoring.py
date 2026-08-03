from dataclasses import dataclass

from app.core.schemas import RouteScore, TaskType
from app.orchestration.circuit_breaker import CircuitBreaker
from app.orchestration.quota import QuotaManager
from app.orchestration.routes import ModelRoute, RouteCatalog
from app.storage.operations import OperationsStore


TASK_FIT: dict[TaskType, dict[str, float]] = {
    "coding": {
        "local_qwen": 25,
        "local_expert": 34,
        "github": 40,
        "groq_strong": 34,
        "gemini": 30,
        "groq_fast": 22,
    },
    "reasoning": {
        "local_qwen": 18,
        "local_expert": 31,
        "groq_strong": 40,
        "gemini": 37,
        "github": 33,
        "groq_fast": 21,
    },
    "summarization": {
        "local_qwen": 18,
        "local_expert": 20,
        "gemini": 42,
        "groq_strong": 36,
        "groq_fast": 30,
        "github": 28,
    },
    "translation": {
        "local_qwen": 18,
        "local_expert": 20,
        "gemini": 42,
        "groq_strong": 35,
        "groq_fast": 29,
        "github": 27,
    },
    "general": {
        "local_qwen": 18,
        "local_expert": 27,
        "gemini": 43,
        "groq_strong": 38,
        "github": 33,
        "groq_fast": 22,
    },
}


@dataclass(frozen=True)
class ScoredRoute:
    route: ModelRoute
    score: float
    eligible: bool
    reasons: list[str]

    def to_schema(self) -> RouteScore:
        return RouteScore(
            route_key=self.route.key,
            provider=self.route.provider,
            model=self.route.model,
            score=round(self.score, 2),
            eligible=self.eligible,
            reasons=self.reasons,
        )


class ProviderScorer:
    def __init__(
        self,
        *,
        catalog: RouteCatalog,
        quota: QuotaManager,
        circuit_breaker: CircuitBreaker,
        store: OperationsStore,
    ) -> None:
        self.catalog = catalog
        self.quota = quota
        self.circuit_breaker = circuit_breaker
        self.store = store

    async def score_all(
        self,
        *,
        task_type: TaskType,
        input_chars: int,
        preferred_routes: list[str] | None = None,
        excluded_routes: list[str] | None = None,
        task_signature: str | None = None,
    ) -> list[ScoredRoute]:
        stats = {
            row["route_key"]: row
            for row in await self.store.route_stats()
        }
        task_stats = (
            {
                row["route_key"]: row
                for row in await self.store.verified_task_route_stats(
                    task_signature
                )
            }
            if task_signature
            and self.catalog.settings.learned_router_mode != "off"
            else {}
        )

        results: list[ScoredRoute] = []

        for route in self.catalog.all():
            reasons: list[str] = []
            score = 0.0
            eligible = True

            if not self.catalog.is_enabled(route):
                eligible = False
                reasons.append(
                    self.catalog.disabled_reason(route)
                    or "Rota devre dışı."
                )

            circuit = await self.circuit_breaker.status(route.key)
            if circuit["open"]:
                eligible = False
                reasons.append(
                    "Circuit breaker geçici olarak açık."
                )

            quota = await self.quota.check_route(route.key)
            if not quota.allowed:
                eligible = False
                reasons.append("Uygulama günlük bütçesi tükendi.")

            task_fit = TASK_FIT[task_type].get(route.key, 20)
            score += task_fit
            reasons.append(f"Görev uyumu +{task_fit:.0f}")

            quality_points = route.quality * 2.0
            score += quality_points
            reasons.append(f"Kalite +{quality_points:.1f}")

            speed_points = route.speed * 1.2
            score += speed_points
            reasons.append(f"Hız +{speed_points:.1f}")

            economy_points = route.economy
            score += economy_points
            reasons.append(f"Ekonomi +{economy_points:.1f}")

            if preferred_routes and route.key in preferred_routes:
                index = preferred_routes.index(route.key)
                preference_bonuses = [30.0, 14.0, 6.0, 1.0]
                bonus = (
                    preference_bonuses[index]
                    if index < len(preference_bonuses)
                    else 0.0
                )
                score += bonus
                label = (
                    "birincil rota"
                    if index == 0
                    else "fallback tercihi"
                )
                reasons.append(
                    f"Agent model tercihi ({label}) +{bonus:.1f}"
                )
                if route.local and index == 0:
                    local_first_bonus = 14.0
                    score += local_first_bonus
                    reasons.append(
                        "Doğrulamalı yerel ilk deneme "
                        f"+{local_first_bonus:.1f}"
                    )

            if excluded_routes and route.key in set(excluded_routes):
                eligible = False
                reasons.append(
                    "Önceki rol kalite kontrolünde reddedildiği için "
                    "bu denemede hariç tutuldu."
                )

            if quota.budget == 0:
                quota_points = 8.0
            else:
                ratio = max(
                    0.0,
                    min(1.0, (quota.remaining or 0) / quota.budget),
                )
                quota_points = ratio * 10.0
            score += quota_points
            reasons.append(f"Kota durumu +{quota_points:.1f}")

            if (
                self.catalog.settings.free_only_mode
                and quota.budget > 0
                and self.catalog.settings.free_quota_conserve_ratio > 0
            ):
                remaining_ratio = max(
                    0.0,
                    min(1.0, (quota.remaining or 0) / quota.budget),
                )
                threshold = (
                    self.catalog.settings.free_quota_conserve_ratio
                )
                if remaining_ratio < threshold:
                    pressure = 1.0 - remaining_ratio / threshold
                    penalty = (
                        pressure
                        * self.catalog.settings
                        .free_quota_max_pressure_penalty
                    )
                    score -= penalty
                    reasons.append(
                        f"Ücretsiz kota koruma cezası -{penalty:.1f}"
                    )

            row = stats.get(route.key)
            if row and row.get("total_calls", 0) >= 2:
                success_rate = float(row.get("success_rate") or 0.0)
                reliability_points = success_rate * 10.0
                score += reliability_points
                reasons.append(
                    f"Geçmiş başarı +{reliability_points:.1f}"
                )

                avg_latency = int(row.get("average_latency_ms") or 0)
                if avg_latency:
                    latency_bonus = max(0.0, 8.0 - avg_latency / 1500.0)
                    score += latency_bonus
                    reasons.append(
                        f"Gerçek gecikme +{latency_bonus:.1f}"
                    )
            else:
                score += 6.0
                reasons.append("Başlangıç güven puanı +6.0")

            learned = task_stats.get(route.key)
            if learned is not None:
                successes = int(learned.get("verified_successes") or 0)
                failures = int(learned.get("verified_failures") or 0)
                observations = successes + failures
                # Beta(2,2) keeps a few lucky outcomes from dominating.
                posterior = (successes + 2) / (observations + 4)
                learned_delta = (posterior - 0.5) * 24.0
                if observations >= 3:
                    if self.catalog.settings.learned_router_mode == "active":
                        score += learned_delta
                        reasons.append(
                            "Görev-özel doğrulanmış rota etkisi "
                            f"{learned_delta:+.1f} ({observations} örnek)"
                        )
                    else:
                        reasons.append(
                            "SHADOW görev-özel rota önerisi "
                            f"{learned_delta:+.1f} ({observations} örnek; "
                            "puana uygulanmadı)"
                        )
                else:
                    reasons.append(
                        "SHADOW rota öğrenimi ısınma aşamasında "
                        f"({observations}/3 doğrulanmış örnek)"
                    )

            # Small models are less suitable for very long contexts even when
            # their nominal context window is large.
            if input_chars > 12_000 and route.key == "groq_fast":
                score -= 12.0
                reasons.append("Uzun girdi cezası -12.0")

            if (
                route.local
                and input_chars
                > self.catalog.settings.local_model_max_input_chars
            ):
                eligible = False
                reasons.append(
                    "Girdi güvenli yerel bağlam sınırını aşıyor."
                )

            if task_type == "reasoning" and input_chars > 6_000:
                if route.key == "groq_strong":
                    score += 5.0
                    reasons.append("Uzun reasoning bonusu +5.0")
                if route.key == "groq_fast":
                    score -= 7.0
                    reasons.append("Reasoning kapasite cezası -7.0")

            if not eligible:
                score = -1_000.0

            results.append(
                ScoredRoute(
                    route=route,
                    score=score,
                    eligible=eligible,
                    reasons=reasons,
                )
            )

        return sorted(results, key=lambda item: item.score, reverse=True)
