from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import secrets
import time
from typing import Any

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.approvals.manager import ApprovalManager
from app.arena.event_telemetry import summarize_arena_events
from app.arena.models import (
    ArenaQuotaPlan,
    ArenaQuotaRoute,
    ArenaResult,
    ArenaScenario,
    ArenaVerificationResult,
)
from app.arena.scoring import score_arena_run
from app.arena.store import ArenaStore
from app.arena.usage import summarize_usage
from app.core.config import Settings
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.routes import RouteCatalog
from app.providers.registry import ProviderRegistry
from app.storage.operations import OperationsStore
from app.supervisor.models import SupervisorCommand
from app.supervisor.service import SupervisorService
from app.tools.base import ToolError
from app.tools.registry import ToolRegistry, build_default_tool_registry


ProgressCallback = Callable[[str, dict[str, Any]], None]


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_workspace_path(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if not relative or posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"Güvensiz Arena yolu: {relative}")
    target = root.joinpath(*posix.parts).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"Arena workspace dışına çıkan yol: {relative}")
    return target


class ArenaRunner:
    def __init__(
        self,
        *,
        project_root: Path,
        workspace_root: Path | None = None,
        history_path: Path | None = None,
        progress: ProgressCallback | None = None,
        local_only: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.workspace_root = (
            workspace_root.resolve()
            if workspace_root
            else self.project_root / "workspace" / "arena"
        )
        self.history = ArenaStore(
            history_path.resolve()
            if history_path
            else self.project_root / "data" / "arena.db"
        )
        self.progress = progress
        self.local_only = local_only

    def _emit(self, event: str, **data: Any) -> None:
        if self.progress:
            self.progress(event, data)

    def _settings(
        self,
        *,
        workspace: Path,
        scenario: ArenaScenario,
    ) -> Settings:
        artifacts = workspace / ".adam"
        provider_overrides: dict[str, str | None] = {}
        if self.local_only:
            provider_overrides = {
                "gemini_api_key": None,
                "github_token": None,
                "groq_api_key": None,
            }
        return Settings(
            _env_file=self.project_root / ".env",
            workspace_root=workspace,
            # Arena must not inherit an open circuit, exhausted retry history,
            # or learned routing state from the user's live workspace.
            operations_database_path=artifacts / "operations.db",
            usage_log_path=artifacts / "usage.jsonl",
            supervisor_database_path=Path(".adam/supervisor.db"),
            project_memory_database_path=Path(".adam/project_memory.db"),
            cache_enabled=False,
            free_only_mode=True,
            paid_models_enabled=False,
            monthly_paid_budget_usd=0.0,
            mission_budget_enabled=True,
            mission_max_model_calls=scenario.max_model_calls,
            mission_max_estimated_input_tokens=(
                scenario.max_estimated_input_tokens
            ),
            supervisor_approval_background=True,
            # Arena runs only fixed scenarios inside a per-run isolated
            # workspace. It deliberately enables trusted autonomy there so
            # benchmark tasks do not require interactive user approvals.
            supervisor_trusted_autonomy_enabled=True,
            **provider_overrides,
        )

    async def quota_plan(self, scenario: ArenaScenario) -> ArenaQuotaPlan:
        probe_workspace = self.workspace_root / "_quota_probe"
        settings = self._settings(
            workspace=probe_workspace,
            scenario=scenario,
        )
        store = OperationsStore(settings.operations_database_path)
        await store.initialize()
        providers = ProviderRegistry(settings)
        try:
            catalog = RouteCatalog(settings=settings, registry=providers)
            rows: list[ArenaQuotaRoute] = []
            has_unlimited = False
            usable_total = 0
            for route in catalog.enabled():
                budget = settings.daily_budget_for_route(route.key)
                used = await store.route_requests_today(route.key)
                if budget == 0:
                    remaining = None
                    reserved = 0
                    usable = None
                    has_unlimited = True
                else:
                    remaining = max(0, budget - used)
                    reserved = math.ceil(
                        budget * settings.free_quota_conserve_ratio
                    )
                    usable = max(0, remaining - reserved)
                    usable_total += usable
                rows.append(
                    ArenaQuotaRoute(
                        key=route.key,
                        provider=route.provider,
                        used=used,
                        budget=budget,
                        remaining=remaining,
                        reserved=reserved,
                        usable_remaining=usable,
                    )
                )

            if not rows:
                return ArenaQuotaPlan(
                    allowed=False,
                    reason="Kullanılabilir ücretsiz sağlayıcı bulunamadı.",
                    minimum_calls=scenario.minimum_calls_to_start,
                    usable_calls=0,
                    routes=(),
                )
            usable_calls = None if has_unlimited else usable_total
            allowed = (
                has_unlimited
                or usable_total >= scenario.minimum_calls_to_start
            )
            reason = (
                "Ücretsiz kota koruma payından sonra Arena için yeterli."
                if allowed
                else (
                    "Ücretsiz kotanın korunan son bölümü kullanılmadan Arena "
                    "başlatılamaz."
                )
            )
            return ArenaQuotaPlan(
                allowed=allowed,
                reason=reason,
                minimum_calls=scenario.minimum_calls_to_start,
                usable_calls=usable_calls,
                routes=tuple(rows),
            )
        finally:
            await providers.close()

    def _new_run(self, scenario: ArenaScenario) -> tuple[str, Path]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{scenario.id}-{timestamp}-{secrets.token_hex(3)}"
        workspace = (self.workspace_root / run_id).resolve()
        root = self.workspace_root.resolve()
        if root not in workspace.parents:
            raise ValueError("Arena çalışma alanı kökü dışında koşu oluşturulamaz.")
        if workspace.exists():
            raise FileExistsError(f"Arena koşu alanı zaten var: {workspace}")
        workspace.mkdir(parents=True)
        return run_id, workspace

    @staticmethod
    def _seed(workspace: Path, scenario: ArenaScenario) -> None:
        for relative, content in scenario.seed_files.items():
            target = _safe_workspace_path(workspace, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    @staticmethod
    def _build_runtime(
        settings: Settings,
        store: OperationsStore,
        providers: ProviderRegistry,
    ) -> tuple[SupervisorService, ToolRegistry]:
        orchestrator = Orchestrator(
            settings=settings,
            registry=providers,
            store=store,
        )
        approvals = ApprovalManager(
            ttl_seconds=settings.approval_ttl_seconds
        )
        tools = build_default_tool_registry(
            settings=settings,
            approvals=approvals,
        )
        agents = build_default_agent_registry(tools.names())
        engine = AgentEngine(
            settings=settings,
            orchestrator=orchestrator,
            tools=tools,
            agents=agents,
        )
        supervisor = SupervisorService(
            settings=settings,
            agent=engine,
            agents=agents,
            tools=tools,
        )
        return supervisor, tools

    @staticmethod
    def _has_runnable_work(command: SupervisorCommand) -> bool:
        for task in command.tasks:
            if task.status == "ready":
                return True
            if (
                task.status == "rework_required"
                and not task.blocked_reason
            ):
                return True
        return False

    @staticmethod
    def _coordination(
        command: SupervisorCommand,
        scenario: ArenaScenario,
    ) -> dict[str, Any]:
        completed_agents = sorted(
            {
                task.assigned_agent
                for task in command.tasks
                if task.status == "completed"
            }
        )
        assignment_agents = {
            handoff.to_agent
            for handoff in command.handoffs
            if handoff.type == "task_assignment"
        }
        completion_agents = {
            handoff.from_agent
            for handoff in command.handoffs
            if handoff.type == "completion"
        }
        required_agents = set(scenario.required_agents)
        handoff_types: dict[str, int] = defaultdict(int)
        for handoff in command.handoffs:
            handoff_types[handoff.type] += 1
        work_sharing_ok = (
            required_agents.issubset(completed_agents)
            and required_agents.issubset(assignment_agents)
            and required_agents.issubset(completion_agents)
            and len(command.handoffs) >= scenario.minimum_handoffs
        )
        if not required_agents and scenario.minimum_handoffs == 0:
            work_sharing_ok = True
        return {
            "required_agents": sorted(required_agents),
            "completed_agents": completed_agents,
            "distinct_completed_agents": len(completed_agents),
            "assignment_agents": sorted(assignment_agents),
            "completion_agents": sorted(completion_agents),
            "handoff_count": len(command.handoffs),
            "handoff_types": dict(sorted(handoff_types.items())),
            "minimum_handoffs": scenario.minimum_handoffs,
            "work_sharing_ok": work_sharing_ok,
            "execution_layers": command.execution_layers,
        }

    @staticmethod
    def _approval_arguments(command: SupervisorCommand, task_id: str) -> dict[str, Any]:
        task = next(item for item in command.tasks if item.id == task_id)
        for record in reversed(task.approval_history):
            if (
                record.approval_id == task.approval_id
                and record.version == task.approval_version
            ):
                return dict(record.arguments or {})
        return {}

    async def _drive(
        self,
        *,
        supervisor: SupervisorService,
        settings: Settings,
        scenario: ArenaScenario,
    ) -> tuple[SupervisorCommand, int, int, str | None]:
        command = await supervisor.create(
            goal=scenario.goal,
            routing_mode="auto",
            auto_start=True,
            background=True,
            autonomy_mode="trusted",
        )
        self._emit("mission_started", mission_id=command.id)
        approvals = 0
        decisions = 0
        local_failure: str | None = None
        last_snapshot: tuple[Any, ...] | None = None
        deadline = time.monotonic() + scenario.timeout_seconds

        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            command = await supervisor.get(command.id)
            counts: defaultdict[str, int] = defaultdict(int)
            for task in command.tasks:
                counts[task.status] += 1
            snapshot = (
                command.status,
                tuple(sorted(counts.items())),
                command.operation_phase,
                command.operation_message,
            )
            if snapshot != last_snapshot:
                self._emit(
                    "state",
                    status=command.status,
                    tasks=dict(counts),
                    phase=command.operation_phase,
                    message=command.operation_message,
                )
                last_snapshot = snapshot

            if command.status == "waiting_decision":
                pending = [
                    decision
                    for decision in command.decisions
                    if decision.status == "pending"
                ]
                if not pending:
                    local_failure = (
                        "Karar bekleniyor durumunda açık karar bulunamadı."
                    )
                    break
                decision = pending[0]
                await supervisor.answer_decision(
                    command_id=command.id,
                    decision_id=decision.id,
                    answer=(
                        "En basit, güvenilir ve ücretsiz çözümü seç; yalnızca "
                        "hedefte izin verilen dosyaları değiştir ve yeni "
                        "bağımlılık ekleme."
                    ),
                    replan_when_complete=True,
                    background=False,
                )
                decisions += 1
                self._emit("decision_answered", decision_id=decision.id)
                continue

            if command.status == "awaiting_approval":
                pending_tasks = [
                    task
                    for task in command.tasks
                    if task.status == "awaiting_approval"
                    and task.approval_state == "pending"
                ]
                if not pending_tasks:
                    continue
                task = pending_tasks[0]
                arguments = self._approval_arguments(command, task.id)
                if (
                    task.approval_tool not in {"workspace_write", "safe_terminal"}
                    or ToolRegistry.is_high_risk(
                        task.approval_tool or "",
                        arguments,
                    )
                ):
                    local_failure = (
                        "Arena güvenli otomatik onay sınırını aşan işlem istedi: "
                        f"{task.approval_tool or 'unknown'}"
                    )
                    self._emit(
                        "approval_blocked",
                        task_id=task.id,
                        tool=task.approval_tool,
                    )
                    break
                await supervisor.approve(
                    command_id=command.id,
                    task_id=task.id,
                    expected_approval_id=task.approval_id,
                    expected_approval_version=task.approval_version,
                    background=False,
                )
                approvals += 1
                self._emit(
                    "approval_applied",
                    task_id=task.id,
                    tool=task.approval_tool,
                )
                continue

            if command.status == "ready":
                if not self._has_runnable_work(command):
                    local_failure = (
                        "Komut hazır görünmesine rağmen çalıştırılabilir görev "
                        "kalmadı; Arena ilerlemesiz döngüyü durdurdu."
                    )
                    self._emit(
                        "no_progress_stopped",
                        tasks=[
                            {
                                "id": task.id,
                                "status": task.status,
                                "recovery_reason": task.recovery_reason,
                            }
                            for task in command.tasks
                        ],
                    )
                    break
                await supervisor.advance(
                    command_id=command.id,
                    max_tasks=settings.supervisor_auto_run_max_tasks,
                    background=False,
                )
                continue

            if command.status in {"completed", "failed"}:
                break
        else:
            local_failure = (
                f"Arena koşusu {scenario.timeout_seconds} saniyeyi aştı."
            )

        command = await supervisor.get(command.id)
        return command, approvals, decisions, local_failure

    @staticmethod
    async def _verify(
        tools: ToolRegistry,
        scenario: ArenaScenario,
    ) -> list[ArenaVerificationResult]:
        results: list[ArenaVerificationResult] = []
        for verification in scenario.verifications:
            try:
                payload = await tools.execute_direct(
                    "safe_terminal",
                    {
                        "preset": verification.preset,
                        "extra_args": list(verification.extra_args),
                    },
                )
                stdout = str(payload.get("stdout") or "")
                stderr = str(payload.get("stderr") or "")
                output = "\n".join(
                    part.strip() for part in (stdout, stderr) if part.strip()
                )
                results.append(
                    ArenaVerificationResult(
                        name=verification.name,
                        preset=verification.preset,
                        success=bool(payload.get("success")),
                        exit_code=payload.get("exit_code"),
                        output=output[-8_000:],
                    )
                )
            except ToolError as exc:
                results.append(
                    ArenaVerificationResult(
                        name=verification.name,
                        preset=verification.preset,
                        success=False,
                        exit_code=None,
                        output=str(exc),
                    )
                )
        return results

    async def run(self, scenario: ArenaScenario) -> ArenaResult:
        quota = await self.quota_plan(scenario)
        self._emit("quota_checked", **quota.to_dict())
        if not quota.allowed:
            raise RuntimeError(quota.reason)

        run_id, workspace = self._new_run(scenario)
        self._seed(workspace, scenario)
        protected_before = {
            path: _sha256(_safe_workspace_path(workspace, path))
            for path in scenario.protected_paths
        }
        settings = self._settings(workspace=workspace, scenario=scenario)
        store = OperationsStore(settings.operations_database_path)
        await store.initialize()
        providers = ProviderRegistry(settings)
        supervisor, tools = self._build_runtime(settings, store, providers)

        started = time.perf_counter()
        command: SupervisorCommand | None = None
        approvals = 0
        decisions = 0
        local_failure: str | None = None
        try:
            baseline_verifications = await self._verify(tools, scenario)
            if (
                scenario.initial_verification_should_fail
                and not any(
                    not item.success and item.exit_code is not None
                    for item in baseline_verifications
                )
            ):
                raise RuntimeError(
                    "Arena başlangıç doğrulaması beklenen gerçek test "
                    "hatasını üretmedi; model çağrısı yapılmadı."
                )
            self._emit(
                "baseline_verified",
                expected_failure=scenario.initial_verification_should_fail,
                results=[
                    {
                        "name": item.name,
                        "success": item.success,
                        "exit_code": item.exit_code,
                    }
                    for item in baseline_verifications
                ],
            )
            command, approvals, decisions, local_failure = await self._drive(
                supervisor=supervisor,
                settings=settings,
                scenario=scenario,
            )
            verifications = await self._verify(tools, scenario)
            missing_required = [
                path
                for path in scenario.required_paths
                if not _safe_workspace_path(workspace, path).is_file()
            ]
            changed_protected = [
                path
                for path, digest in protected_before.items()
                if _sha256(_safe_workspace_path(workspace, path)) != digest
            ]
            usage = summarize_usage(
                usage_log=settings.usage_log_path,
                mission_id=command.id,
            )
            mission_usage = await store.mission_usage(command.id)
            reserved_calls = int(
                (mission_usage or {}).get("reserved_calls", 0)
            )
            usage["reserved_calls"] = reserved_calls
            usage["model_calls"] = max(
                int(usage["events"]),
                reserved_calls,
            )
            task_attempts = sum(task.attempts for task in command.tasks)
            failure_records = sum(
                len(task.failure_history) for task in command.tasks
            )
            coordination = self._coordination(command, scenario)
            context_compiler = (
                await supervisor.project_memory.context_compiler_summary()
            )
            effective_status = (
                "timed_out"
                if local_failure
                and "saniyeyi aştı" in local_failure
                else (
                    "stalled"
                    if local_failure
                    and "ilerlemesiz döngüyü" in local_failure
                    else command.status
                )
            )
            score = score_arena_run(
                scenario=scenario,
                status=effective_status,
                verification_passed=sum(
                    int(item.success) for item in verifications
                ),
                verification_total=len(verifications),
                required_paths_ok=not missing_required,
                protected_paths_ok=not changed_protected,
                approvals=approvals,
                decisions=decisions,
                model_calls=int(usage["model_calls"]),
                total_tokens=int(usage["total_tokens"]),
                failed_calls=int(usage["failed_calls"]),
                task_attempts=task_attempts,
                task_count=len(command.tasks),
                failure_records=failure_records,
                work_sharing_ok=bool(
                    coordination["work_sharing_ok"]
                ),
            )
            elapsed = round(time.perf_counter() - started, 3)
            event_counts, notable_events = summarize_arena_events(
                command.events
            )
            result = ArenaResult(
                run_id=run_id,
                scenario_id=scenario.id,
                scenario_title=scenario.title,
                mission_id=command.id,
                status=effective_status,
                failure_reason=local_failure or command.failure_reason,
                elapsed_seconds=elapsed,
                workspace=str(workspace),
                approvals_applied=approvals,
                decisions_answered=decisions,
                required_paths_ok=not missing_required,
                missing_required_paths=missing_required,
                protected_paths_ok=not changed_protected,
                changed_protected_paths=changed_protected,
                baseline_verifications=baseline_verifications,
                verifications=verifications,
                usage=usage,
                mission_usage=mission_usage,
                task_attempts=task_attempts,
                failure_records=failure_records,
                score=score,
                coordination=coordination,
                context_compiler=context_compiler,
                handoffs=[
                    handoff.model_dump()
                    for handoff in command.handoffs
                ],
                tasks=[
                    {
                        "id": task.id,
                        "title": task.title,
                        "agent": task.assigned_agent,
                        "status": task.status,
                        "attempts": task.attempts,
                        "verification": (
                            task.effective_verification
                            or task.verification
                        ),
                        "files": task.materialized_files,
                        "failure_history": [
                            failure.model_dump()
                            for failure in task.failure_history
                        ],
                    }
                    for task in command.tasks
                ],
                event_counts=event_counts,
                notable_events=notable_events,
                last_events=[
                    event.model_dump() for event in command.events[-30:]
                ],
            )
            artifacts = workspace / ".adam"
            artifacts.mkdir(parents=True, exist_ok=True)
            (artifacts / "arena-result.json").write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.history.record(result)
            self._emit(
                "run_finished",
                status=result.status,
                score=result.score.total,
                workspace=result.workspace,
            )
            return result
        finally:
            await providers.close()
