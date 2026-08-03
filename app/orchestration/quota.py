from dataclasses import dataclass

from app.core.config import Settings
from app.storage.operations import OperationsStore


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    used: int
    budget: int
    remaining: int | None
    reason: str


@dataclass(frozen=True)
class MissionBudgetDecision:
    allowed: bool
    usage_scope: str | None
    calls_used: int
    calls_budget: int
    estimated_input_tokens_used: int
    estimated_input_tokens_budget: int
    reason: str


class QuotaManager:
    def __init__(
        self,
        *,
        settings: Settings,
        store: OperationsStore,
    ) -> None:
        self.settings = settings
        self.store = store

    async def check_route(self, route_key: str) -> QuotaDecision:
        budget = self.settings.daily_budget_for_route(route_key)
        used = await self.store.route_requests_today(route_key)

        if budget == 0:
            return QuotaDecision(
                allowed=True,
                used=used,
                budget=budget,
                remaining=None,
                reason="Uygulama içi günlük tavan devre dışı.",
            )

        remaining = max(0, budget - used)
        return QuotaDecision(
            allowed=used < budget,
            used=used,
            budget=budget,
            remaining=remaining,
            reason=(
                "Günlük uygulama bütçesi uygun."
                if used < budget
                else "Günlük uygulama bütçesi tükendi."
            ),
        )

    async def reserve_route_call(self, route_key: str) -> QuotaDecision:
        decision = await self.check_route(route_key)
        if decision.allowed:
            await self.store.increment_route_request(route_key)
        return decision

    async def check_mission(
        self,
        *,
        usage_scope: str | None,
        estimated_input_tokens: int,
    ) -> MissionBudgetDecision:
        if not self.settings.mission_budget_enabled or not usage_scope:
            return MissionBudgetDecision(
                allowed=True,
                usage_scope=usage_scope,
                calls_used=0,
                calls_budget=self.settings.mission_max_model_calls,
                estimated_input_tokens_used=0,
                estimated_input_tokens_budget=(
                    self.settings
                    .mission_max_estimated_input_tokens
                ),
                reason="Misyon bütçe sayacı uygulanmadı.",
            )
        usage = await self.store.mission_usage(usage_scope)
        calls_used = int((usage or {}).get("reserved_calls", 0))
        estimated_used = int(
            (usage or {}).get("estimated_input_tokens", 0)
        )
        calls_allowed = (
            calls_used < self.settings.mission_max_model_calls
        )
        tokens_allowed = (
            estimated_used + max(0, estimated_input_tokens)
            <= self.settings.mission_max_estimated_input_tokens
        )
        reason = "Misyon ücretsiz bütçesi uygun."
        if not calls_allowed:
            reason = "Misyon model çağrısı bütçesi tükendi."
        elif not tokens_allowed:
            reason = "Misyon tahmini giriş token bütçesi tükendi."
        return MissionBudgetDecision(
            allowed=calls_allowed and tokens_allowed,
            usage_scope=usage_scope,
            calls_used=calls_used,
            calls_budget=self.settings.mission_max_model_calls,
            estimated_input_tokens_used=estimated_used,
            estimated_input_tokens_budget=(
                self.settings.mission_max_estimated_input_tokens
            ),
            reason=reason,
        )

    async def reserve_mission_call(
        self,
        *,
        usage_scope: str | None,
        estimated_input_tokens: int,
    ) -> MissionBudgetDecision:
        if not self.settings.mission_budget_enabled or not usage_scope:
            return await self.check_mission(
                usage_scope=usage_scope,
                estimated_input_tokens=estimated_input_tokens,
            )
        result = await self.store.reserve_mission_call(
            usage_scope=usage_scope,
            estimated_input_tokens=estimated_input_tokens,
            max_calls=self.settings.mission_max_model_calls,
            max_estimated_input_tokens=(
                self.settings.mission_max_estimated_input_tokens
            ),
        )
        return MissionBudgetDecision(
            allowed=bool(result["allowed"]),
            usage_scope=usage_scope,
            calls_used=int(result["calls_used"]),
            calls_budget=int(result["calls_budget"]),
            estimated_input_tokens_used=int(
                result["estimated_input_tokens_used"]
            ),
            estimated_input_tokens_budget=int(
                result["estimated_input_tokens_budget"]
            ),
            reason=str(result["reason"]),
        )

    async def check_verify_mode(self) -> QuotaDecision:
        budget = self.settings.verify_daily_budget
        used = await self.store.mode_requests_today("verify")

        if budget == 0:
            return QuotaDecision(
                allowed=False,
                used=used,
                budget=budget,
                remaining=0,
                reason="Verify modu günlük bütçesi 0.",
            )

        remaining = max(0, budget - used)
        return QuotaDecision(
            allowed=used < budget,
            used=used,
            budget=budget,
            remaining=remaining,
            reason=(
                "Verify bütçesi uygun."
                if used < budget
                else "Verify günlük bütçesi tükendi."
            ),
        )

    async def reserve_verify_mode(self) -> QuotaDecision:
        decision = await self.check_verify_mode()
        if decision.allowed:
            await self.store.increment_mode_request("verify")
        return decision
