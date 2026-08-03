import asyncio
import time
from dataclasses import dataclass

from app.core.config import Settings
from app.core.schemas import (
    CandidateResponse,
    FailedProvider,
    OrchestrateRequest,
    OrchestrateResponse,
    RouteScore,
    TaskType,
)
from app.orchestration.cache import make_cache_key
from app.orchestration.circuit_breaker import CircuitBreaker
from app.orchestration.quality import inspect_response
from app.orchestration.quota import QuotaManager
from app.orchestration.router import TaskClassifier
from app.orchestration.routes import ModelRoute, RouteCatalog
from app.orchestration.scoring import ProviderScorer, ScoredRoute
from app.orchestration.smart_router import SmartModelRouter
from app.orchestration.usage_log import UsageLog
from app.providers.base import ProviderRequest, ProviderResponse
from app.providers.registry import ProviderRegistry
from app.storage.operations import OperationsStore


JUDGE_PROMPT = """
Sen bir baş cevap düzenleyicisisin. Kullanıcının isteğini ve aşağıdaki aday
cevapları incele. Doğru, uygulanabilir ve eksiksiz kısımları birleştir.
Adaylarda çelişki varsa çoğunluğu otomatik olarak doğru kabul etme.
Yanlış veya doğrulanamayan iddiaları çıkar. Yalnızca kullanıcıya verilecek
nihai cevabı yaz; değerlendirme sürecini anlatma.
""".strip()


@dataclass(frozen=True)
class ExecutionPlan:
    task_type: TaskType
    routes: list[ModelRoute]
    reason: str
    scores: list[RouteScore]


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        registry: ProviderRegistry,
        store: OperationsStore,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.store = store
        self.catalog = RouteCatalog(settings=settings, registry=registry)
        self.classifier = TaskClassifier()
        self.quota = QuotaManager(settings=settings, store=store)
        self.usage_log = UsageLog(settings.usage_log_path)
        self.semaphore = asyncio.Semaphore(settings.max_parallel_providers)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_failure_threshold,
            cooldown_seconds=settings.circuit_cooldown_seconds,
        )
        self.scorer = ProviderScorer(
            catalog=self.catalog,
            quota=self.quota,
            circuit_breaker=self.circuit_breaker,
            store=store,
        )
        self.smart_router = SmartModelRouter(
            default_routes=settings.fallback_routes,
        )

    def _validate_size(self, request: OrchestrateRequest) -> int:
        total = len(request.system_prompt) + sum(
            len(message.content)
            for message in request.normalized_messages()
        )
        if total > self.settings.max_input_chars:
            raise ValueError(
                f"Girdi çok uzun: {total} karakter. "
                f"Sınır: {self.settings.max_input_chars}."
            )
        return total

    def _provider_request(
        self,
        request: OrchestrateRequest,
        route: ModelRoute,
    ) -> ProviderRequest:
        requested_tokens = (
            request.max_output_tokens
            or self.settings.max_output_tokens
        )
        if route.key == "groq_fast":
            requested_tokens = min(
                requested_tokens,
                self.settings.groq_fast_max_output_tokens,
            )
        if route.local:
            requested_tokens = min(
                requested_tokens,
                self.settings.ollama_max_output_tokens,
            )

        quality_policy = (
            "\n\nKalite kuralları: Aynı cümleyi veya paragrafı tekrar etme. "
            "Soruyu doğrudan ve tutarlı biçimde yanıtla. Bir tekrar döngüsü "
            "başlarsa cevabı uzatmak yerine bitir."
        )

        return ProviderRequest(
            messages=request.normalized_messages(),
            system_prompt=request.system_prompt + quality_policy,
            temperature=request.temperature,
            max_output_tokens=requested_tokens,
            model=route.model,
            usage_scope=request.usage_scope,
            usage_task_id=request.usage_task_id,
            local=route.local,
        )

    def _provider_wall_timeout(
        self,
        provider_request: ProviderRequest,
    ) -> float:
        if getattr(provider_request, "local", False):
            if provider_request.model == self.settings.ollama_expert_model:
                return self.settings.local_expert_timeout_seconds
            return self.settings.local_model_timeout_seconds
        # Short answers should fail over quickly. Large focused-file
        # generations receive more time, up to the configured hard ceiling.
        adaptive = 20.0 + provider_request.max_output_tokens / 128.0
        return min(
            self.settings.provider_call_wall_timeout_seconds,
            max(5.0, adaptive),
        )

    async def _route_precheck(
        self,
        route: ModelRoute,
    ) -> tuple[bool, str]:
        if not self.catalog.is_enabled(route):
            return (
                False,
                self.catalog.disabled_reason(route)
                or "Rota etkin değil.",
            )

        allowed, retry_after = await self.circuit_breaker.can_call(route.key)
        if not allowed:
            return (
                False,
                f"Circuit breaker açık; yaklaşık {retry_after} saniye sonra "
                "yeniden denenecek.",
            )

        quota = await self.quota.check_route(route.key)
        if not quota.allowed:
            return (
                False,
                f"{quota.reason} Kullanılan: {quota.used}/{quota.budget}.",
            )

        return True, "Uygun."

    async def _call(
        self,
        route: ModelRoute,
        provider_request: ProviderRequest,
    ) -> ProviderResponse:
        input_chars = len(provider_request.system_prompt) + sum(
            len(message.content)
            for message in provider_request.messages
        )
        estimated_input_tokens = (input_chars + 3) // 4
        precheck_ok, precheck_reason = await self._route_precheck(route)
        if not precheck_ok:
            raise RuntimeError(precheck_reason)

        if route.local:
            # Local inference is still bounded by the AgentEngine model-call
            # ceiling, but it must not consume scarce remote API mission quota.
            mission_budget = await self.quota.check_mission(
                usage_scope=None,
                estimated_input_tokens=0,
            )
        else:
            mission_budget = await self.quota.reserve_mission_call(
                usage_scope=provider_request.usage_scope,
                estimated_input_tokens=estimated_input_tokens,
            )
        if not mission_budget.allowed:
            raise RuntimeError(
                f"{mission_budget.reason} "
                f"Çağrı: {mission_budget.calls_used}/"
                f"{mission_budget.calls_budget}; tahmini giriş tokenı: "
                f"{mission_budget.estimated_input_tokens_used}/"
                f"{mission_budget.estimated_input_tokens_budget}."
            )

        reservation = await self.quota.reserve_route_call(route.key)
        if not reservation.allowed:
            raise RuntimeError(reservation.reason)

        provider = self.registry.get(route.provider)
        started = time.perf_counter()
        wall_timeout = self._provider_wall_timeout(provider_request)

        try:
            async with self.semaphore:
                try:
                    result = await asyncio.wait_for(
                        provider.generate(provider_request),
                        timeout=wall_timeout,
                    )
                except TimeoutError as exc:
                    raise RuntimeError(
                        f"{route.label} toplam yanıt süresi "
                        f"{wall_timeout:.1f} saniyeyi aştı; ücretsiz "
                        "fallback rotasına geçiliyor."
                    ) from exc
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self.circuit_breaker.record_failure(
                route.key,
                immediate=route.local,
            )
            await self.store.record_route_call(
                route_key=route.key,
                provider=route.provider,
                model=route.model,
                success=False,
                latency_ms=latency_ms,
                error=str(exc),
            )
            await self.usage_log.write(
                {
                    "route_key": route.key,
                    "provider": route.provider,
                    "model": route.model,
                    "success": False,
                    "local": route.local,
                    "latency_ms": latency_ms,
                    "input_chars": input_chars,
                    "estimated_input_tokens": estimated_input_tokens,
                    "usage_scope": provider_request.usage_scope,
                    "usage_task_id": provider_request.usage_task_id,
                    "mission_calls_used": mission_budget.calls_used,
                    "mission_calls_budget": mission_budget.calls_budget,
                    "mission_estimated_input_tokens_used": (
                        mission_budget.estimated_input_tokens_used
                    ),
                    "mission_estimated_input_tokens_budget": (
                        mission_budget.estimated_input_tokens_budget
                    ),
                    "error": str(exc),
                }
            )
            raise

        await self.circuit_breaker.record_success(route.key)

        rate_limit = result.rate_limit or {}
        await self.store.record_route_call(
            route_key=route.key,
            provider=result.provider,
            model=result.model,
            success=True,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            remote_request_limit=rate_limit.get("request_limit"),
            remote_requests_remaining=rate_limit.get("requests_remaining"),
        )
        if provider_request.usage_scope and not route.local:
            await self.store.record_mission_tokens(
                usage_scope=provider_request.usage_scope,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
        await self.usage_log.write(
            {
                "route_key": route.key,
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "input_chars": input_chars,
                "estimated_input_tokens": estimated_input_tokens,
                "usage_scope": provider_request.usage_scope,
                "usage_task_id": provider_request.usage_task_id,
                "mission_calls_used": mission_budget.calls_used,
                "mission_calls_budget": mission_budget.calls_budget,
                "mission_estimated_input_tokens_used": (
                    mission_budget.estimated_input_tokens_used
                ),
                "mission_estimated_input_tokens_budget": (
                    mission_budget.estimated_input_tokens_budget
                ),
                "success": True,
                "local": route.local,
                "finish_reason": result.finish_reason,
            }
        )
        return result

    async def _call_with_failure(
        self,
        route: ModelRoute,
        provider_request: ProviderRequest,
    ) -> tuple[ProviderResponse | None, FailedProvider | None]:
        try:
            result = await self._call(route, provider_request)
            return result, None
        except Exception as exc:
            return (
                None,
                FailedProvider(
                    route_key=route.key,
                    provider=route.provider,
                    error=str(exc),
                ),
            )

    async def preview_scores(
        self,
        *,
        messages,
    ) -> tuple[TaskType, list[RouteScore]]:
        task_type = self.classifier.classify(messages)
        input_chars = sum(len(message.content) for message in messages)
        scored = await self.scorer.score_all(
            task_type=task_type,
            input_chars=input_chars,
        )
        return task_type, [item.to_schema() for item in scored]

    async def _plan(
        self,
        request: OrchestrateRequest,
        input_chars: int,
    ) -> ExecutionPlan:
        messages = request.normalized_messages()
        task_type = (
            request.task_type_override
            or self.classifier.classify(messages)
        )
        routing_advice = self.smart_router.classify_and_route(
            "\n".join(
                message.content
                for message in messages
                if message.role == "user"
            ),
            preferred_routes=request.preferred_routes,
            excluded_routes=request.excluded_routes,
            prefer_local=self.settings.local_model_enabled,
            estimated_tokens=request.max_output_tokens or 500,
        )
        scored = await self.scorer.score_all(
            task_type=task_type,
            input_chars=input_chars,
            preferred_routes=list(routing_advice.preferred_routes),
            excluded_routes=request.excluded_routes,
            task_signature=request.task_signature,
        )
        score_schemas = [item.to_schema() for item in scored]

        if request.mode == "direct":
            route = self.catalog.get(request.provider or "")
            return ExecutionPlan(
                task_type=task_type,
                routes=[route],
                reason=f"Direct modunda {route.label} seçildi.",
                scores=score_schemas,
            )

        if request.mode == "economy":
            excluded = set(request.excluded_routes or [])
            routes = [
                self.catalog.get(key)
                for key in self.settings.fallback_routes
                if key not in excluded
            ]
            if not routes:
                raise RuntimeError(
                    "Economy modunda kalite sonrası uygun rota kalmadı."
                )
            return ExecutionPlan(
                task_type=task_type,
                routes=routes,
                reason="Economy modu yapılandırılmış fallback sırasını kullandı.",
                scores=score_schemas,
            )

        if request.mode in {"verify", "council"}:
            if request.providers:
                routes = [
                    self.catalog.get(key)
                    for key in request.providers
                ]
            else:
                routes = [
                    item.route
                    for item in scored
                    if item.eligible
                ][:2]

            return ExecutionPlan(
                task_type=task_type,
                routes=routes,
                reason=(
                    "Verify/council modu en yüksek puanlı uygun rotaları "
                    "paralel kullanacak."
                ),
                scores=score_schemas,
            )

        # Auto mode: sorted score order itself is fallback order.
        routes = [
            item.route
            for item in scored
            if item.eligible
        ]
        if not routes:
            raise RuntimeError("Auto modunda uygun model rotası bulunamadı.")

        winner = scored[0]
        return ExecutionPlan(
            task_type=task_type,
            routes=routes,
            reason=(
                f"Auto puanlama sonucu {winner.route.label} "
                f"{winner.score:.1f} puanla ilk sırada. "
                f"{routing_advice.reason}"
            ),
            scores=score_schemas,
        )

    def _response(
        self,
        *,
        request: OrchestrateRequest,
        route: ModelRoute,
        result: ProviderResponse,
        plan: ExecutionPlan,
        failures: list[FailedProvider],
        calls_used: int,
        candidates: list[tuple[ModelRoute, ProviderResponse]] | None = None,
        total_latency_ms: int | None = None,
    ) -> OrchestrateResponse:
        exposed_candidates = None
        if request.include_candidates and candidates:
            exposed_candidates = [
                CandidateResponse(
                    route_key=item_route.key,
                    provider=item_result.provider,
                    model=item_result.model,
                    content=item_result.content,
                    latency_ms=item_result.latency_ms,
                    input_tokens=item_result.input_tokens,
                    output_tokens=item_result.output_tokens,
                )
                for item_route, item_result in candidates
            ]

        return OrchestrateResponse(
            answer=result.content,
            mode=request.mode,
            selected_route=route.key,
            selected_provider=result.provider,
            model=result.model,
            finish_reason=result.finish_reason,
            latency_ms=total_latency_ms or result.latency_ms,
            task_type=plan.task_type,
            route_reason=plan.reason,
            calls_used=calls_used,
            routing_scores=plan.scores,
            candidates=exposed_candidates,
            failures=failures,
        )

    async def _fallback(
        self,
        request: OrchestrateRequest,
        plan: ExecutionPlan,
    ) -> OrchestrateResponse:
        failures: list[FailedProvider] = []
        started = time.perf_counter()
        calls_used = 0

        seen: set[str] = set()
        for route in plan.routes:
            if route.key in seen:
                continue
            seen.add(route.key)

            precheck_ok, precheck_reason = await self._route_precheck(route)
            if not precheck_ok:
                failures.append(
                    FailedProvider(
                        route_key=route.key,
                        provider=route.provider,
                        error=precheck_reason,
                    )
                )
                continue

            calls_used += 1
            result, failure = await self._call_with_failure(
                route,
                self._provider_request(request, route),
            )
            if failure:
                failures.append(failure)
                continue

            assert result is not None

            quality = inspect_response(result.content)
            if not quality.accepted:
                await self.circuit_breaker.record_failure(route.key)
                failures.append(
                    FailedProvider(
                        route_key=route.key,
                        provider=route.provider,
                        error=(
                            "Model cevabı kalite kontrolünde reddedildi: "
                            + quality.reason
                        ),
                    )
                )
                continue

            return self._response(
                request=request,
                route=route,
                result=result,
                plan=plan,
                failures=failures,
                calls_used=calls_used,
                total_latency_ms=int(
                    (time.perf_counter() - started) * 1000
                ),
            )

        raise RuntimeError(
            "Hiçbir model rotasından cevap alınamadı. "
            + "; ".join(
                f"{item.route_key}: {item.error}"
                for item in failures
            )
        )

    async def _multi_model(
        self,
        request: OrchestrateRequest,
        plan: ExecutionPlan,
    ) -> OrchestrateResponse:
        verify_quota = await self.quota.reserve_verify_mode()
        if not verify_quota.allowed:
            raise RuntimeError(
                f"{verify_quota.reason} "
                f"Kullanılan: {verify_quota.used}/{verify_quota.budget}."
            )

        started = time.perf_counter()
        failures: list[FailedProvider] = []
        available: list[ModelRoute] = []

        for route in plan.routes:
            allowed, reason = await self._route_precheck(route)
            if allowed:
                available.append(route)
            else:
                failures.append(
                    FailedProvider(
                        route_key=route.key,
                        provider=route.provider,
                        error=reason,
                    )
                )

        # Do not call the same provider twice in parallel if avoidable.
        unique_provider_routes: list[ModelRoute] = []
        providers_seen: set[str] = set()
        for route in available:
            if route.provider in providers_seen:
                continue
            providers_seen.add(route.provider)
            unique_provider_routes.append(route)
            if len(unique_provider_routes) == 2:
                break

        if len(unique_provider_routes) < 2:
            fallback_plan = ExecutionPlan(
                task_type=plan.task_type,
                routes=available or plan.routes,
                reason=(
                    plan.reason
                    + " İki farklı uygun sağlayıcı bulunamadığı için "
                    "fallback çalıştırıldı."
                ),
                scores=plan.scores,
            )
            return await self._fallback(request, fallback_plan)

        pairs = await asyncio.gather(
            *[
                self._call_with_failure(
                    route,
                    self._provider_request(request, route),
                )
                for route in unique_provider_routes
            ]
        )
        calls_used = len(unique_provider_routes)

        candidates: list[tuple[ModelRoute, ProviderResponse]] = []
        for route, (result, failure) in zip(unique_provider_routes, pairs):
            if result is not None:
                quality = inspect_response(result.content)
                if quality.accepted:
                    candidates.append((route, result))
                else:
                    await self.circuit_breaker.record_failure(route.key)
                    failures.append(
                        FailedProvider(
                            route_key=route.key,
                            provider=route.provider,
                            error=(
                                "Model cevabı kalite kontrolünde reddedildi: "
                                + quality.reason
                            ),
                        )
                    )
            if failure is not None:
                failures.append(failure)

        if not candidates:
            raise RuntimeError("Bütün aday model rotaları başarısız oldu.")

        if len(candidates) == 1:
            route, result = candidates[0]
            return self._response(
                request=request,
                route=route,
                result=result,
                plan=plan,
                failures=failures,
                calls_used=calls_used,
                candidates=candidates,
                total_latency_ms=int(
                    (time.perf_counter() - started) * 1000
                ),
            )

        candidate_text = "\n\n".join(
            f"### Aday {index + 1} — {route.label}\n{result.content}"
            for index, (route, result) in enumerate(candidates)
        )

        message_type = type(request.normalized_messages()[0])
        judge_messages = request.normalized_messages() + [
            message_type(
                role="user",
                content=(
                    "Aşağıdaki aday cevaplardan nihai cevabı oluştur:\n\n"
                    + candidate_text
                ),
            )
        ]

        # The fastest successful candidate is judge, provided its route still
        # has quota. This avoids a fourth provider and keeps verify affordable.
        judge_route, _ = min(
            candidates,
            key=lambda item: item[1].latency_ms,
        )
        judge_request = ProviderRequest(
            messages=judge_messages,
            system_prompt=JUDGE_PROMPT,
            temperature=0.1,
            max_output_tokens=(
                request.max_output_tokens
                or self.settings.max_output_tokens
            ),
            model=judge_route.model,
        )

        judge_ok, judge_reason = await self._route_precheck(judge_route)
        if judge_ok:
            calls_used += 1
            judge, judge_failure = await self._call_with_failure(
                judge_route,
                judge_request,
            )
        else:
            judge = None
            judge_failure = FailedProvider(
                route_key=judge_route.key,
                provider=judge_route.provider,
                error=judge_reason,
            )

        if judge_failure:
            failures.append(judge_failure)
            judge_route, judge = candidates[0]

        assert judge is not None
        return self._response(
            request=request,
            route=judge_route,
            result=judge,
            plan=ExecutionPlan(
                task_type=plan.task_type,
                routes=plan.routes,
                reason=(
                    plan.reason
                    + " İki farklı sağlayıcı cevap üretti; hızlı başarılı "
                    "rota judge olarak sentez yaptı."
                ),
                scores=plan.scores,
            ),
            failures=failures,
            calls_used=calls_used,
            candidates=candidates,
            total_latency_ms=int(
                (time.perf_counter() - started) * 1000
            ),
        )

    async def run(
        self,
        request: OrchestrateRequest,
    ) -> OrchestrateResponse:
        input_chars = self._validate_size(request)

        if not self.registry.names():
            raise RuntimeError(
                "Hiçbir model sağlayıcısı etkin değil. Yerel modeli "
                "etkinleştir veya .env dosyasına en az bir API anahtarı ekle."
            )

        plan = await self._plan(request, input_chars)

        cacheable = (
            self.settings.cache_enabled
            and not request.bypass_cache
            and request.mode in {"economy", "auto", "direct"}
        )
        cache_key = make_cache_key(request) if cacheable else None

        if cache_key:
            cached_json = await self.store.get_cached(cache_key)
            if cached_json:
                cached = OrchestrateResponse.model_validate_json(cached_json)
                cached.cache_hit = True
                cached.calls_used = 0
                cached.latency_ms = 0
                cached.route_reason = (
                    cached.route_reason + " Aynı istek cache üzerinden döndü."
                )
                return cached

        mission_budget = await self.quota.check_mission(
            usage_scope=request.usage_scope,
            estimated_input_tokens=(input_chars + 3) // 4,
        )
        if not mission_budget.allowed:
            local_routes = [route for route in plan.routes if route.local]
            if not local_routes:
                raise RuntimeError(
                    f"{mission_budget.reason} Prometheus ücretli rotaya geçmedi. "
                    f"Çağrı: {mission_budget.calls_used}/"
                    f"{mission_budget.calls_budget}; tahmini giriş tokenı: "
                    f"{mission_budget.estimated_input_tokens_used}/"
                    f"{mission_budget.estimated_input_tokens_budget}."
                )
            plan = ExecutionPlan(
                task_type=plan.task_type,
                routes=local_routes,
                reason=(
                    plan.reason
                    + " Uzak misyon bütçesi tükendi; yalnızca ücretsiz "
                    "yerel rota kullanılabilir."
                ),
                scores=plan.scores,
            )

        if request.mode in {"verify", "council"}:
            result = await self._multi_model(request, plan)
        else:
            result = await self._fallback(request, plan)

        if cache_key and not result.failures:
            await self.store.set_cached(
                cache_key,
                result.model_dump_json(),
                self.settings.cache_ttl_seconds,
            )

        return result
