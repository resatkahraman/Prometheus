from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import json
import posixpath
import re
import secrets
import shlex
import time
import unicodedata
from typing import Any, Awaitable, Coroutine, TypeVar

from app.agent.engine import AgentEngine
from app.agents.registry import AgentRegistry
from app.core.config import Settings
from app.core.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStep,
    ProjectRunPreviewRequest,
    ProjectRunPreviewResponse,
    ProjectRunPreviewTask,
    ProjectRunCommitRequest,
    ProjectRunCommitResponse,
    RunFileChange,
    RunChangeReviewResponse,
    RunRevertRequest,
    RunRevertResponse,
    ProjectRunHistoryResponse,
    ProjectRunHistoryItem,
    ProjectRunHistoryTaskSummary,
    ProjectRunRetryRequest,
    ProjectRunRetryResponse,
)
from app.supervisor.run_snapshots import RunSnapshotManager
from app.workspace.policy import WorkspacePolicy
from app.tools.base import ToolError
from app.memory.attention import AttentionBroker
from app.memory.context_compiler import ContextCompiler, ContextSegment
from app.memory.project import FileMemory, ProjectMemoryStore
from app.improvement.service import ImprovementService
from app.improvement.forge import PrometheusForge
from app.planning.integrity import validate_planning_document
from app.planning.kernel import TypedPlanningKernel
from app.planning.models import PlanTask, PlanningDocument
from app.planning.parser import parse_planning_document
from app.security.autonomy import (
    ensure_autonomy_mode_allowed,
    trusted_autonomy_enabled,
)
from app.supervisor.failure_intelligence import classify_verification_failure
from app.supervisor.contract_repair import build_fastapi_status_code_repair
from app.supervisor.tdd_self_fix import (
    TDDSelfFixLoop,
    TDDSelfFixMaxRetriesExceeded,
)
from app.supervisor.checkpoints import (
    MissionCheckpointStore,
    MissionCheckpointError,
    MissionCheckpointIntegrityError,
    DuplicateMissionCheckpointError,
    compute_state_hash,
    compute_canonical_checkpoint_hash,
)
from app.supervisor.execution_receipts import (
    ExecutionReceiptStore,
    ExecutionReceiptError,
    ExecutionReceiptIntegrityError,
    DuplicateExecutionReceiptError,
)
from app.supervisor.event_journal import (
    MissionEventJournal,
    MissionEventIntegrityError,
    canonical_event_kind,
    compute_canonical_event_hash,
    sanitize_payload,
)
from app.supervisor.recovery import (
    FailureSignal,
    MAX_MISSION_RECOVERIES,
    MAX_RECOVERY_ATTEMPTS_PER_FAILURE,
    classify_mission_failure,
)
from app.supervisor.history import (
    MAX_MISSION_HISTORY_RECORDS,
    MissionHistoryIntegrityError,
    MissionHistoryLimitError,
    build_mission_history_page,
    build_mission_post_run_summary,
)
from app.supervisor.models import (
    ExecutionReceipt,
    ExecutionReceiptIntegrity,
    ExecutionReceiptPage,
    ExecutionReceiptSummary,
    MissionCheckpointIntegrity,
    MissionCheckpointPage,
    MissionCheckpointRecord,
    MissionControlResponse,
    MissionEventIntegrity,
    MissionEventPage,
    MissionEventRecord,
    MissionStateProjection,
    MissionFailureClassification,
    MissionHistoryPage,
    MissionPostRunSummary,
    MissionRecoveryStatusResponse,
    RecoverMissionResponse,
    SupervisorApprovalRecord,
    SupervisorCommand,
    SupervisorDecision,
    SupervisorEvent,
    SupervisorFailureRecord,
    SupervisorHandoff,
    SupervisorTask,
    utc_now,
)
from app.supervisor.store import SupervisorCommandStore
from app.tools.registry import ToolRegistry
from app.tools.base import ToolApprovalRequired, ToolError
from app.tools.fingerprint import tool_fingerprint
from app.tools.terminal import TERMINAL_RUNTIME_REVISION
from app.workspace.policy import WorkspacePolicy


FOCUSED_GENERATION_REVISION = (
    "focused-file-v4-safe-patch-isolated-verification"
)


_ACCEPT = re.compile(r"^\s*(?:#+\s*)?(KABUL|ACCEPT|APPROVE)\b", re.IGNORECASE)
_REJECT = re.compile(r"^\s*(?:#+\s*)?(RET|REJECT)\b", re.IGNORECASE)

T = TypeVar("T")


class SupervisorService:
    def __init__(
        self,
        *,
        settings: Settings,
        agent: AgentEngine,
        agents: AgentRegistry,
        tools: ToolRegistry,
        event_journal: MissionEventJournal | None = None,
        execution_receipt_store: ExecutionReceiptStore | None = None,
        mission_checkpoint_store: MissionCheckpointStore | None = None,
    ) -> None:
        self.settings = settings
        self.workspace = WorkspacePolicy(
            root=settings.workspace_root,
            max_file_bytes=settings.workspace_max_file_bytes,
            max_search_results=settings.workspace_max_search_results,
        )
        self.agent = agent
        self.agents = agents
        self.tools = tools
        self._event_journal = event_journal
        self._execution_receipt_store = execution_receipt_store
        self._mission_checkpoint_store = mission_checkpoint_store
        database_path = None
        if settings.supervisor_persistence_enabled:
            database_path = settings.supervisor_database_path
            if not database_path.is_absolute():
                database_path = settings.workspace_root / database_path
        self.store = SupervisorCommandStore(
            ttl_seconds=settings.supervisor_command_ttl_seconds,
            max_events=settings.supervisor_max_events,
            database_path=database_path,
        )
        self._background_tasks: set[asyncio.Task] = set()
        self._background_jobs: dict[
            tuple[str, str], asyncio.Task
        ] = {}
        self._command_locks: dict[str, asyncio.Lock] = {}
        self.planning_kernel = TypedPlanningKernel(
            tools=tools,
            read_max_lines=settings.supervisor_planner_read_max_lines,
        )
        memory_path = settings.project_memory_database_path
        if not memory_path.is_absolute():
            memory_path = settings.workspace_root / memory_path
        self.project_memory = ProjectMemoryStore(
            Path(memory_path),
            enabled=settings.project_memory_enabled,
        )
        self.attention_broker = AttentionBroker()
        self.context_compiler = ContextCompiler()
        self.improvement = ImprovementService(settings)
        self.snapshot_manager = RunSnapshotManager()
        self.forge = PrometheusForge(
            settings=settings,
            improvement=self.improvement,
        )

    def _get_event_journal(self) -> MissionEventJournal:
        if getattr(self, "_event_journal", None) is not None:
            return self._event_journal
        store = getattr(self, "store", None)
        state_root = store.state_root if store and hasattr(store, "state_root") else None
        persistence_enabled = (
            getattr(self.settings, "supervisor_persistence_enabled", False)
            if hasattr(self, "settings")
            else False
        )
        journal = MissionEventJournal(
            root=state_root,
            persistence_enabled=persistence_enabled,
        )
        self._event_journal = journal
        return journal

    def _get_execution_receipt_store(self) -> ExecutionReceiptStore:
        if getattr(self, "_execution_receipt_store", None) is not None:
            return self._execution_receipt_store
        store = getattr(self, "store", None)
        state_root = store.state_root if store and hasattr(store, "state_root") else None
        persistence_enabled = (
            getattr(self.settings, "supervisor_persistence_enabled", False)
            if hasattr(self, "settings")
            else False
        )
        receipt_store = ExecutionReceiptStore(
            root=state_root,
            persistence_enabled=persistence_enabled,
        )
        self._execution_receipt_store = receipt_store
        return receipt_store

    def _get_mission_checkpoint_store(self) -> MissionCheckpointStore:
        if getattr(self, "_mission_checkpoint_store", None) is not None:
            return self._mission_checkpoint_store
        store = getattr(self, "store", None)
        state_root = store.state_root if store and hasattr(store, "state_root") else None
        persistence_enabled = (
            getattr(self.settings, "supervisor_persistence_enabled", False)
            if hasattr(self, "settings")
            else False
        )
        checkpoint_store = MissionCheckpointStore(
            root=state_root,
            persistence_enabled=persistence_enabled,
        )
        self._mission_checkpoint_store = checkpoint_store
        return checkpoint_store

    def _build_resumable_checkpoint_snapshot(
        self,
        command: SupervisorCommand,
    ) -> dict[str, Any]:
        active_task = next((t for t in command.tasks if t.status == "running"), None)
        current_task_id = active_task.id if active_task else None

        tasks_snap = [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "attempts": t.attempts,
                "assigned_agent": t.assigned_agent,
                "verification": t.verification,
                "exact_files": list(t.exact_files) if t.exact_files else [],
                "continuation_resumes": t.continuation_resumes,
                "recovery_reason": t.recovery_reason,
            }
            for t in command.tasks
        ]

        decisions_snap = [
            {
                "id": d.id,
                "question": d.question,
                "status": d.status,
                "answer": d.answer,
            }
            for d in command.decisions
        ]

        snapshot = {
            "id": command.id,
            "goal": command.goal,
            "status": command.status,
            "autonomy_mode": command.autonomy_mode,
            "auto_run": command.auto_run,
            "plan_text": command.plan_text,
            "tasks": tasks_snap,
            "decisions": decisions_snap,
            "execution_layers": command.execution_layers,
            "current_task_id": current_task_id,
            "control_version": command.control_version,
            "resume_count": command.resume_count,
        }
        return snapshot

    async def _create_mission_checkpoint(
        self,
        command: SupervisorCommand,
        *,
        reason: str,
        resumable: bool,
        resume_target_status: str | None,
        current_task_id: str | None = None,
    ) -> MissionCheckpointRecord:
        checkpoint_store = self._get_mission_checkpoint_store()
        now = datetime.now(timezone.utc)
        snapshot = self._build_resumable_checkpoint_snapshot(command)

        pending_apps = [
            app_t.id for app_t in command.tasks
            if app_t.status == "awaiting_approval" or getattr(app_t, "pending_approval_id", None)
        ]

        rec = checkpoint_store.append(
            mission_id=command.id,
            reason=reason,
            created_at=now,
            status_at_checkpoint=command.status,
            resume_target_status=resume_target_status,
            current_task_id=current_task_id,
            pending_approval_ids=pending_apps,
            state_version=command.control_version,
            state_snapshot=snapshot,
            resumable=resumable,
        )

        summary_payload = {
            "checkpoint_id": rec.checkpoint_id,
            "checkpoint_sequence": rec.sequence,
            "checkpoint_hash": rec.checkpoint_hash,
            "state_hash": rec.state_hash,
            "reason": rec.reason,
            "resumable": rec.resumable,
            "status_at_checkpoint": rec.status_at_checkpoint,
            "resume_target_status": rec.resume_target_status,
            "current_task_id": rec.current_task_id,
            "pending_approval_count": len(rec.pending_approval_ids),
            "snapshot_size_bytes": rec.snapshot_size_bytes,
        }

        self._event(
            command,
            type="checkpoint_created",
            message=f"Created mission checkpoint {rec.checkpoint_id} (seq {rec.sequence})",
            task_id=current_task_id,
            data=summary_payload,
        )
        await self.store.put(command)

        return rec

    async def _pause_at_safe_boundary_if_requested(
        self,
        command: SupervisorCommand,
        *,
        boundary: str,
        current_task_id: str | None = None,
    ) -> bool:
        if not command.pause_requested:
            return False
        if command.status in {"completed", "failed", "cancelled", "reverted"}:
            command.pause_requested = False
            await self.store.put(command)
            return False

        target_status = command.status
        if target_status == "running":
            target_status = "ready"

        now = datetime.now(timezone.utc)
        command.status = "paused"
        command.pause_requested = False
        command.paused_at = now
        command.resume_target_status = target_status
        command.control_version += 1
        await self.store.put(command)

        rec = await self._create_mission_checkpoint(
            command=command,
            reason="pause_boundary",
            resumable=True,
            resume_target_status=target_status,
            current_task_id=current_task_id,
        )

        command.active_checkpoint_id = rec.checkpoint_id
        self._clear_operation(command)
        self._event(
            command,
            type="mission_paused",
            message=f"Mission paused at boundary '{boundary}'. Active checkpoint: {rec.checkpoint_id}",
            task_id=current_task_id,
            data={
                "boundary": boundary,
                "active_checkpoint_id": rec.checkpoint_id,
                "resume_target_status": target_status,
                "control_version": command.control_version,
            },
        )
        await self.store.put(command)
        return True

    async def request_mission_pause(
        self,
        command_id: str,
        *,
        reason: str | None = None,
        expected_control_version: int | None = None,
    ) -> MissionControlResponse:
        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            if command.status in {"completed", "failed", "cancelled", "reverted"}:
                raise ValueError(f"Terminal command '{command_id}' pause edilemez.")

            if expected_control_version is not None and command.control_version != expected_control_version:
                raise ValueError(
                    f"Control version mismatch: expected {expected_control_version}, current is {command.control_version}."
                )

            if command.status == "paused":
                return MissionControlResponse(
                    mission_id=command_id,
                    command_status=command.status,
                    pause_requested=False,
                    active_checkpoint_id=command.active_checkpoint_id,
                    control_version=command.control_version,
                    resume_count=command.resume_count,
                    message="Mission zaten paused durumunda.",
                )

            if command.pause_requested:
                return MissionControlResponse(
                    mission_id=command_id,
                    command_status=command.status,
                    pause_requested=True,
                    active_checkpoint_id=command.active_checkpoint_id,
                    control_version=command.control_version,
                    resume_count=command.resume_count,
                    message="Pause talebi zaten alındı, güvenli sınır bekleniyor.",
                )

            now = datetime.now(timezone.utc)
            command.pause_requested = True
            command.pause_requested_at = now
            command.pause_reason = (reason or "").strip()[:2000] if reason else None
            command.control_version += 1

            self._event(
                command,
                type="mission_pause_requested",
                message=f"Mission pause requested: {command.pause_reason or 'No reason provided'}",
                data={
                    "reason": command.pause_reason,
                    "control_version": command.control_version,
                },
            )
            await self.store.put(command)

            if command.status in {"ready", "awaiting_approval", "waiting_decision"}:
                await self._pause_at_safe_boundary_if_requested(
                    command,
                    boundary="immediate_idle",
                )

            return MissionControlResponse(
                mission_id=command_id,
                command_status=command.status,
                pause_requested=command.pause_requested,
                active_checkpoint_id=command.active_checkpoint_id,
                control_version=command.control_version,
                resume_count=command.resume_count,
                message="Pause talebi kaydedildi." if command.pause_requested else "Mission paused durumuna geçti.",
            )

    async def create_mission_checkpoint(
        self,
        command_id: str,
    ) -> MissionCheckpointRecord:
        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            if command.status == "running" and any(t.status == "running" for t in command.tasks):
                raise ValueError("Aktif çalışan görev esnasında manuel checkpoint oluşturulamaz.")

            rec = await self._create_mission_checkpoint(
                command=command,
                reason="manual",
                resumable=False,
                resume_target_status=None,
            )
            return rec

    async def resume_mission(
        self,
        command_id: str,
        *,
        checkpoint_id: str | None = None,
        expected_control_version: int | None = None,
    ) -> MissionControlResponse:
        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            if command.status != "paused":
                raise ValueError(f"Command '{command_id}' paused durumunda değil (mevcut: {command.status}).")

            if not command.active_checkpoint_id:
                raise ValueError(f"Command '{command_id}' için aktif checkpoint bulunamadı.")

            if checkpoint_id and checkpoint_id != command.active_checkpoint_id:
                raise ValueError(
                    f"Checkpoint mismatch: requested '{checkpoint_id}', active is '{command.active_checkpoint_id}'."
                )

            if expected_control_version is not None and command.control_version != expected_control_version:
                raise ValueError(
                    f"Control version mismatch: expected {expected_control_version}, current is {command.control_version}."
                )

            checkpoint_store = self._get_mission_checkpoint_store()
            checkpoint = checkpoint_store.get_checkpoint(
                mission_id=command_id,
                checkpoint_id=command.active_checkpoint_id,
            )
            if checkpoint is None:
                raise KeyError(f"Active checkpoint '{command.active_checkpoint_id}' store'da bulunamadı.")

            if not checkpoint.resumable:
                raise ValueError(f"Checkpoint '{checkpoint.checkpoint_id}' resumable değil.")

            snapshot = checkpoint_store.get_checkpoint_snapshot(
                mission_id=command_id,
                checkpoint_id=command.active_checkpoint_id,
            )
            if snapshot is None:
                raise KeyError(f"Active checkpoint snapshot '{command.active_checkpoint_id}' okunamadı.")

            calc_state_hash, _ = compute_state_hash(snapshot)
            current_snapshot = self._build_resumable_checkpoint_snapshot(command)
            current_state_hash, _ = compute_state_hash(current_snapshot)

            if current_state_hash != calc_state_hash or current_state_hash != checkpoint.state_hash:
                raise ValueError("State hash conflict: mission durumu checkpoint snapshot'ı ile eşleşmiyor.")

            target_status = command.resume_target_status or "ready"

            self._event(
                command,
                type="mission_resume_started",
                message=f"Resuming mission from checkpoint {checkpoint.checkpoint_id}",
                data={
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "resume_target_status": target_status,
                    "control_version": command.control_version + 1,
                },
            )

            command.active_checkpoint_id = None
            command.pause_requested = False
            command.pause_requested_at = None
            command.pause_reason = None
            command.paused_at = None
            command.resume_target_status = None
            command.resume_count += 1
            command.control_version += 1
            command.status = target_status
            await self.store.put(command)

            self._event(
                command,
                type="mission_resumed",
                message=f"Mission resumed successfully (target status: {target_status}).",
                data={
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "target_status": target_status,
                    "resume_count": command.resume_count,
                    "control_version": command.control_version,
                },
            )
            await self.store.put(command)

            if target_status in {"ready", "running"}:
                self._spawn(
                    self.advance(
                        command_id=command.id,
                        background=True,
                    ),
                    command_id=command.id,
                    operation="resume_advance",
                )

            return MissionControlResponse(
                mission_id=command_id,
                command_status=command.status,
                pause_requested=False,
                active_checkpoint_id=None,
                control_version=command.control_version,
                resume_count=command.resume_count,
                message="Mission başarıyla devralındı ve sürdürüldü.",
            )

    async def _record_mission_failure(
        self,
        *,
        command: SupervisorCommand,
        phase: str,
        error_code: str,
        safe_message: str,
        task: SupervisorTask | None = None,
        source_receipt_id: str | None = None,
        exception: BaseException | None = None,
        receipt_outcome: str | None = None,
        verification_failed: bool = False,
    ) -> MissionFailureClassification:
        classification = classify_mission_failure(
            FailureSignal(
                mission_id=command.id,
                phase=phase,
                error_code=error_code,
                safe_message=safe_message,
                task_id=task.id if task else None,
                source_receipt_id=source_receipt_id,
                task_attempt=task.attempts if task else 0,
                exception=exception,
                receipt_outcome=receipt_outcome,
                verification_failed=verification_failed,
            ),
            mission_recovery_count=command.recovery_count,
        )
        latest = command.latest_failure
        if (
            latest is not None
            and latest.failure_fingerprint == classification.failure_fingerprint
            and command.recovery_status in {"eligible", "blocked", "exhausted"}
        ):
            return latest

        command.latest_failure = classification
        command.recovery_attempts_for_failure = 0
        command.recovery_checkpoint_id = None
        command.recovery_task_id = None
        command.recovery_started_at = None
        command.recovery_completed_at = None
        command.recovery_status = "eligible" if classification.recoverable else "blocked"
        if task is not None:
            task.recovery_reason = (
                task.recovery_reason
                or f"mission_failure:{classification.category}"[:160]
            )

        self._event(
            command,
            type="mission_failure_classified",
            task_id=classification.task_id,
            message="Mission failure deterministically classified.",
            data={
                "failure_id": classification.failure_id,
                "failure_fingerprint": classification.failure_fingerprint,
                "task_id": classification.task_id,
                "source_receipt_id": classification.source_receipt_id,
                "phase": classification.phase,
                "category": classification.category,
                "severity": classification.severity,
                "error_code": classification.error_code,
                "retryable": classification.retryable,
                "recoverable": classification.recoverable,
                "recommended_action": classification.recommended_action,
                "task_attempt": classification.task_attempt,
                "mission_recovery_count": classification.mission_recovery_count,
            },
        )
        await self.store.put(command)
        return classification

    def _recovery_blocked_reason(
        self,
        command: SupervisorCommand,
    ) -> str | None:
        failure = command.latest_failure
        if failure is None:
            return "no_failure"
        if not failure.recoverable or failure.recommended_action != "retry_task":
            return "failure_not_recoverable"
        if command.recovery_status != "eligible":
            return f"recovery_{command.recovery_status}"
        if command.recovery_attempts_for_failure >= MAX_RECOVERY_ATTEMPTS_PER_FAILURE:
            return "failure_recovery_limit_exhausted"
        if command.recovery_count >= MAX_MISSION_RECOVERIES:
            return "mission_recovery_limit_exhausted"
        if command.pause_requested or command.status == "paused" or command.active_checkpoint_id:
            return "mission_resume_required"
        if self._active_task(command) is not None:
            return "active_task"
        if command.active_operation:
            return "active_operation"
        if any(key[0] == command.id and not job.done() for key, job in self._background_jobs.items()):
            return "active_background_job"
        task = next((item for item in command.tasks if item.id == failure.task_id), None)
        if task is None:
            return "recovery_task_not_found"
        if task.status not in {"failed", "rework_required"}:
            return "invalid_task_state"
        if task.attempts >= self.settings.supervisor_max_task_attempts:
            return "task_attempt_limit_exhausted"
        return None

    async def get_mission_recovery_status(
        self,
        command_id: str,
    ) -> MissionRecoveryStatusResponse:
        command = await self.store.get(command_id)
        blocked_reason = self._recovery_blocked_reason(command)
        return MissionRecoveryStatusResponse(
            mission_id=command.id,
            command_status=command.status,
            recovery_status=command.recovery_status,
            latest_failure=command.latest_failure,
            recovery_attempts_for_failure=command.recovery_attempts_for_failure,
            recovery_count=command.recovery_count,
            recovery_checkpoint_id=command.recovery_checkpoint_id,
            recovery_task_id=command.recovery_task_id,
            recovery_started_at=command.recovery_started_at,
            recovery_completed_at=command.recovery_completed_at,
            control_version=command.control_version,
            can_recover=blocked_reason is None,
            blocked_reason=blocked_reason,
        )

    @staticmethod
    def _recover_response(
        command: SupervisorCommand,
        *,
        accepted: bool,
        scheduled: bool,
        idempotent: bool,
        message: str,
    ) -> RecoverMissionResponse:
        failure = command.latest_failure
        if failure is None or not failure.task_id:
            raise ValueError("Mission için görev bağlı kurtarılabilir hata yok.")
        return RecoverMissionResponse(
            mission_id=command.id,
            failure_id=failure.failure_id,
            task_id=failure.task_id,
            accepted=accepted,
            scheduled=scheduled,
            idempotent=idempotent,
            command_status=command.status,
            recovery_status=command.recovery_status,
            recovery_attempts_for_failure=command.recovery_attempts_for_failure,
            recovery_count=command.recovery_count,
            recovery_checkpoint_id=command.recovery_checkpoint_id,
            control_version=command.control_version,
            message=message,
        )

    async def recover_mission(
        self,
        command_id: str,
        *,
        failure_id: str | None = None,
        expected_control_version: int | None = None,
    ) -> RecoverMissionResponse:
        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            failure = command.latest_failure
            if failure is None:
                raise ValueError("Mission için sınıflandırılmış hata yok.")
            if failure_id is not None and failure_id != failure.failure_id:
                raise ValueError("Failure identity mismatch.")
            if expected_control_version is not None and expected_control_version != command.control_version:
                raise ValueError("Control version mismatch.")
            if command.recovery_status in {"scheduled", "running", "recovered"}:
                return self._recover_response(
                    command,
                    accepted=True,
                    scheduled=command.recovery_status in {"scheduled", "running"},
                    idempotent=True,
                    message="Recovery request was already accepted.",
                )

            blocked_reason = self._recovery_blocked_reason(command)
            if blocked_reason is not None:
                if blocked_reason.endswith("limit_exhausted"):
                    command.recovery_status = "exhausted"
                    await self.store.put(command)
                raise ValueError(f"Mission recovery blocked: {blocked_reason}.")

            task = next((item for item in command.tasks if item.id == failure.task_id), None)
            if task is None:
                raise KeyError("Recovery task not found.")
            checkpoint = await self._create_mission_checkpoint(
                command,
                reason="system",
                resumable=False,
                resume_target_status=None,
                current_task_id=task.id,
            )
            command.recovery_status = "scheduled"
            command.recovery_attempts_for_failure += 1
            command.recovery_count += 1
            command.recovery_checkpoint_id = checkpoint.checkpoint_id
            command.recovery_task_id = task.id
            command.recovery_started_at = datetime.now(timezone.utc)
            command.recovery_completed_at = None
            command.control_version += 1
            task.status = "rework_required"
            if task.recovery_reason and task.recovery_reason.startswith("mission_failure:"):
                task.recovery_reason = None
            self._refresh_task_states(command)
            recovery_payload = {
                "failure_id": failure.failure_id,
                "task_id": task.id,
                "category": failure.category,
                "recovery_attempts_for_failure": command.recovery_attempts_for_failure,
                "recovery_count": command.recovery_count,
                "recovery_checkpoint_id": checkpoint.checkpoint_id,
                "control_version": command.control_version,
                "scheduled": False,
            }
            self._event(
                command,
                type="mission_recovery_started",
                task_id=task.id,
                message="Explicit Mission recovery accepted.",
                data=recovery_payload,
            )
            await self.store.put(command)
            spawned = self._spawn(
                self.advance(command_id=command.id, background=True),
                command_id=command.id,
                operation="mission_recovery",
            )
            if not spawned:
                equivalent = self._background_jobs.get((command.id, "mission_recovery"))
                if equivalent is not None and not equivalent.done():
                    return self._recover_response(
                        command,
                        accepted=True,
                        scheduled=True,
                        idempotent=True,
                        message="Equivalent recovery is already scheduled.",
                    )
                command.recovery_status = "blocked"
                self._event(
                    command,
                    type="mission_recovery_blocked",
                    task_id=task.id,
                    message="Mission recovery could not be scheduled.",
                    data={**recovery_payload, "scheduled": False},
                )
                await self.store.put(command)
                raise ValueError("Mission recovery scheduling failed.")
            self._event(
                command,
                type="mission_recovery_scheduled",
                task_id=task.id,
                message="Mission recovery scheduled through Supervisor advance.",
                data={**recovery_payload, "scheduled": True},
            )
            await self.store.put(command)
            return self._recover_response(
                command,
                accepted=True,
                scheduled=True,
                idempotent=False,
                message="Mission recovery scheduled.",
            )

    async def _finalize_mission_recovery_if_needed(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> None:
        if command.recovery_status not in {"scheduled", "running"} or task.id != command.recovery_task_id:
            return
        if task.status not in {"completed", "reviewing", "awaiting_approval"}:
            return
        command.recovery_status = "recovered"
        command.recovery_completed_at = datetime.now(timezone.utc)
        failure = command.latest_failure
        self._event(
            command,
            type="mission_recovery_completed",
            task_id=task.id,
            message="Mission recovery restored execution continuity.",
            data={
                "failure_id": failure.failure_id if failure else "unknown",
                "task_id": task.id,
                "category": failure.category if failure else "unknown",
                "recovery_attempts_for_failure": command.recovery_attempts_for_failure,
                "recovery_count": command.recovery_count,
                "recovery_checkpoint_id": command.recovery_checkpoint_id,
                "control_version": command.control_version,
                "scheduled": False,
            },
        )
        await self.store.put(command)

    async def _record_execution_receipt(
        self,
        *,
        mission_id: str,
        execution_kind: str,
        actor_kind: str,
        actor_id: str,
        started_at: datetime,
        completed_at: datetime,
        outcome: str,
        request_summary: str,
        input_value: Any = None,
        result_value: Any = None,
        receipt_id: str | None = None,
        tool_name: str | None = None,
        worker_role: str | None = None,
        task_id: str | None = None,
        step_id: str | None = None,
        approval_id: str | None = None,
        sandbox_id: str | None = None,
        capabilities: list[str] | None = None,
        filesystem_scope: list[str] | None = None,
        network_access: list[str] | None = None,
        exit_code: int | None = None,
        affected_files: list[str] | None = None,
        stdout_preview: str | None = None,
        stderr_preview: str | None = None,
        artifact_ids: list[str] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionReceipt:
        receipt_store = self._get_execution_receipt_store()

        receipt = receipt_store.append(
            mission_id=mission_id,
            execution_kind=execution_kind,
            actor_kind=actor_kind,
            actor_id=actor_id,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
            request_summary=request_summary,
            input_value=input_value,
            result_value=result_value,
            receipt_id=receipt_id,
            tool_name=tool_name,
            worker_role=worker_role,
            task_id=task_id,
            step_id=step_id,
            approval_id=approval_id,
            sandbox_id=sandbox_id,
            capabilities=capabilities,
            filesystem_scope=filesystem_scope,
            network_access=network_access,
            exit_code=exit_code,
            affected_files=affected_files,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            artifact_ids=artifact_ids,
            error_code=error_code,
            error_message=error_message,
            metadata=metadata,
        )

        store = getattr(self, "store", None)
        command = await store.get(mission_id) if store else None
        if command:
            summary_payload = {
                "receipt_id": receipt.receipt_id,
                "receipt_sequence": receipt.sequence,
                "receipt_hash": receipt.receipt_hash,
                "execution_kind": receipt.execution_kind,
                "actor_id": receipt.actor_id,
                "outcome": receipt.outcome,
                "task_id": receipt.task_id,
                "duration_ms": receipt.duration_ms,
                "affected_file_count": len(receipt.affected_files),
                "artifact_count": len(receipt.artifact_ids),
            }
            self._event(
                command,
                type="execution_receipt_recorded",
                message=f"Recorded execution receipt {receipt.receipt_id} (seq {receipt.sequence})",
                task_id=task_id,
                data=summary_payload,
            )
            await store.put(command)

        return receipt

    @classmethod
    def _event(
        cls_or_self: Any,
        command: SupervisorCommand,
        *,
        type: str,
        message: str,
        task_id: str | None = None,
        approval_id: str | None = None,
        actor: str = "supervisor",
        data: dict[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        if isinstance(cls_or_self, SupervisorCommand):
            cmd = cls_or_self
            service_inst = None
        else:
            cmd = command
            service_inst = cls_or_self if isinstance(cls_or_self, SupervisorService) else None

        cmd.events.append(
            SupervisorEvent(
                sequence=len(cmd.events) + 1,
                type=type,
                message=message,
                task_id=task_id,
                data=data or {},
            )
        )

        # Journal payload snapshot
        caller_data = dict(data or {})
        if payload:
            caller_data.update(dict(payload))
        caller_data["message"] = message

        task_stat: str | None = None
        app_state: str | None = None
        if task_id:
            for t in cmd.tasks:
                if t.id == task_id:
                    task_stat = t.status
                    app_state = t.approval_state
                    break

        pending_app_ids: list[str] = []
        for t in cmd.tasks:
            if t.approval_id and t.approval_state == "pending":
                if t.approval_id not in pending_app_ids:
                    pending_app_ids.append(t.approval_id)

        proj_run = bool(
            cmd.project_run_preview_digest and cmd.project_run_workspace_path
        )

        caller_data["command_status"] = cmd.status
        caller_data["task_status"] = task_stat
        caller_data["approval_state"] = app_state
        caller_data["pending_approval_ids"] = pending_app_ids
        caller_data["project_run"] = proj_run

        if service_inst is not None:
            journal = service_inst._get_event_journal()
        else:
            journal = MissionEventJournal(root=None, persistence_enabled=False)

        journal.append(
            mission_id=cmd.id,
            event_type=type,
            occurred_at=datetime.now(timezone.utc),
            task_id=task_id,
            approval_id=approval_id,
            actor=actor or "supervisor",
            payload=caller_data,
        )

    def _command_lock(self, command_id: str) -> asyncio.Lock:
        lock = self._command_locks.get(command_id)
        if lock is None:
            lock = asyncio.Lock()
            self._command_locks[command_id] = lock
        return lock

    @staticmethod
    def _approval_record(
        task: SupervisorTask,
        *,
        approval_id: str,
        approval_version: int,
    ) -> SupervisorApprovalRecord | None:
        return next(
            (
                record
                for record in task.approval_history
                if record.approval_id == approval_id
                and record.version == approval_version
            ),
            None,
        )

    @classmethod
    def _upsert_approval_record(
        cls,
        task: SupervisorTask,
        *,
        approval_id: str,
        approval_version: int,
        phase: str,
        state: str,
        tool: str | None = None,
        description: str | None = None,
        preview: dict[str, Any] | None = None,
        arguments: dict[str, Any] | None = None,
        fingerprint: str | None = None,
        message: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        success: bool | None = None,
        result: Any | None = None,
    ) -> SupervisorApprovalRecord:
        record = cls._approval_record(
            task,
            approval_id=approval_id,
            approval_version=approval_version,
        )
        if record is None:
            record = SupervisorApprovalRecord(
                version=approval_version,
                approval_id=approval_id,
                phase=phase,
                state=state,
                tool=tool,
                description=description,
                preview=preview,
                arguments=arguments,
                fingerprint=fingerprint,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
                success=success,
                result=result,
            )
            task.approval_history.append(record)
            return record

        record.state = state
        if tool is not None:
            record.tool = tool
        if description is not None:
            record.description = description
        if preview is not None:
            record.preview = preview
        if arguments is not None:
            record.arguments = arguments
        if fingerprint is not None:
            record.fingerprint = fingerprint
        if message is not None:
            record.message = message
        if started_at is not None:
            record.started_at = started_at
        if finished_at is not None:
            record.finished_at = finished_at
        if success is not None:
            record.success = success
        if result is not None:
            record.result = result
        return record

    @staticmethod
    def _next_pending_approval(
        command: SupervisorCommand,
    ) -> SupervisorTask | None:
        return next(
            (
                task
                for task in command.tasks
                if task.approval_state == "pending"
                and task.status == "awaiting_approval"
            ),
            None,
        )

    @staticmethod
    def _clear_approval_payload(
        task: SupervisorTask,
        *,
        state: str = "idle",
        message: str | None = None,
    ) -> None:
        task.agent_session_id = None
        task.approval_id = None
        task.approval_phase = None
        task.approval_tool = None
        task.approval_description = None
        task.approval_preview = None
        task.approval_expires_at = None
        task.processing_approval_id = None
        task.approval_state = state
        task.last_approval_message = message

    def _set_pending_approval(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        response: AgentResponse,
        phase: str,
    ) -> None:
        pending = response.pending_approval
        if response.session_id is None or pending is None:
            task.status = "rework_required"
            self._clear_approval_payload(
                task,
                state="failed",
                message=(
                    "Agent onay beklediğini bildirdi fakat geçerli "
                    "oturum/onay bilgisi üretmedi."
                ),
            )
            self._event(
                command,
                type="approval_payload_invalid",
                task_id=task.id,
                message=task.last_approval_message or "Geçersiz onay.",
            )
            return

        task.status = "awaiting_approval"
        task.agent_session_id = response.session_id
        task.approval_id = pending.id
        task.approval_phase = phase
        task.approval_version += 1
        task.approval_state = "pending"
        task.approval_tool = pending.tool_name
        task.approval_description = pending.description
        task.approval_preview = pending.preview
        task.approval_expires_at = pending.expires_at
        task.processing_approval_id = None
        task.last_approval_message = (
            f"{pending.tool_name} işlemi kullanıcı onayı bekliyor."
        )
        self._upsert_approval_record(
            task,
            approval_id=pending.id,
            approval_version=task.approval_version,
            phase=phase,
            state="pending",
            tool=pending.tool_name,
            description=pending.description,
            preview=pending.preview,
            arguments=pending.arguments,
            fingerprint=tool_fingerprint(
                pending.tool_name,
                pending.arguments,
            ),
            message=task.last_approval_message,
        )
        command.status = "awaiting_approval"
        self._set_operation(
            command,
            operation=f"approval:{task.id}",
            phase="waiting_for_user",
            message=task.last_approval_message,
            attempt=task.approval_version,
            route=response.final_route,
            reset_started_at=True,
        )

    @staticmethod
    def _has_applied_tool_evidence(response: AgentResponse) -> bool:
        for step in response.trace or []:
            result = step.tool_result
            if not isinstance(result, dict):
                continue
            if step.tool == "workspace_write" and result.get("changed") is True:
                return True
            if step.tool == "safe_terminal" and result.get("success") is True:
                return True
        return False

    @staticmethod
    def _operation_task_id(operation: str) -> str | None:
        match = re.match(
            r"^(?:task|review|approval|continuation):"
            r"(?P<task_id>TASK-\d{3})$",
            operation,
        )
        return match.group("task_id") if match else None

    @staticmethod
    def _active_task(
        command: SupervisorCommand,
        *,
        exclude_task_id: str | None = None,
    ) -> SupervisorTask | None:
        active_states = {"running", "awaiting_approval", "reviewing"}
        return next(
            (
                task
                for task in command.tasks
                if task.id != exclude_task_id
                and (
                    task.status in active_states
                    or task.approval_state == "processing"
                )
            ),
            None,
        )

    @staticmethod
    def _clear_operation_if(
        command: SupervisorCommand,
        operation: str,
    ) -> None:
        if command.active_operation == operation:
            SupervisorService._clear_operation(command)

    async def _recover_background_operation(
        self,
        *,
        command_id: str,
        operation: str,
        reason: str,
        event_type: str,
    ) -> None:
        try:
            command = await self.store.get(command_id)
        except KeyError:
            return

        task_id = self._operation_task_id(operation)
        if task_id is None:
            command.status = "failed"
            command.failure_reason = reason
            self._clear_operation_if(command, operation)
            self._event(
                command,
                type=event_type,
                message=reason,
                data={"operation": operation},
            )
            await self.store.put(command)
            return

        task = next(
            (item for item in command.tasks if item.id == task_id),
            None,
        )
        if task is None:
            return

        if task.status not in {"completed", "awaiting_approval"}:
            task.status = "rework_required"
            task.recovery_reason = "background_operation_interrupted"
            task.last_approval_message = reason
        command.failure_reason = None
        self._clear_operation_if(command, operation)
        self._event(
            command,
            type=event_type,
            task_id=task.id,
            message=reason,
            data={"operation": operation},
        )
        self._refresh_task_states(command)
        await self.store.put(command)

    async def _cancel_background_job(
        self,
        *,
        command_id: str,
        operation: str,
    ) -> None:
        job = self._background_jobs.get((command_id, operation))
        if job is not None and not job.done():
            await self._cancel_with_grace(job)

    def _spawn(
        self,
        coroutine: Coroutine[Any, Any, Any],
        *,
        command_id: str,
        operation: str,
    ) -> bool:
        key = (command_id, operation)
        existing = self._background_jobs.get(key)
        if existing is not None and not existing.done():
            coroutine.close()
            return False

        async def guarded() -> None:
            try:
                await coroutine
            except asyncio.CancelledError:
                # Watchdog/restart cancellation is recovered by the caller.
                raise
            except Exception as exc:
                await self._recover_background_operation(
                    command_id=command_id,
                    operation=operation,
                    reason=(
                        f"{operation} arka plan görevi beklenmedik biçimde "
                        f"durdu: {type(exc).__name__}: {exc}"
                    ),
                    event_type="background_crashed",
                )

        task = asyncio.create_task(
            guarded(),
            name=f"prometheus:{operation}:{command_id}",
        )
        self._background_tasks.add(task)
        self._background_jobs[key] = task

        def cleanup(done: asyncio.Task) -> None:
            self._background_tasks.discard(done)
            if self._background_jobs.get(key) is done:
                self._background_jobs.pop(key, None)

        task.add_done_callback(cleanup)
        return True

    @staticmethod
    def _set_operation(
        command: SupervisorCommand,
        *,
        operation: str,
        phase: str,
        message: str,
        attempt: int = 0,
        max_attempts: int = 0,
        route: str | None = None,
        reset_started_at: bool = False,
    ) -> None:
        now = utc_now()
        if (
            reset_started_at
            or command.active_operation != operation
            or not command.operation_started_at
        ):
            command.operation_started_at = now

        command.active_operation = operation
        command.operation_phase = phase
        command.operation_message = message
        command.operation_attempt = attempt
        command.operation_max_attempts = max_attempts
        command.operation_route = route
        command.last_heartbeat_at = now

    @staticmethod
    def _heartbeat(
        command: SupervisorCommand,
        *,
        message: str | None = None,
        phase: str | None = None,
    ) -> None:
        command.last_heartbeat_at = utc_now()
        if message:
            command.operation_message = message
        if phase:
            command.operation_phase = phase

    @staticmethod
    def _clear_operation(command: SupervisorCommand) -> None:
        command.active_operation = None
        command.operation_phase = None
        command.operation_message = None
        command.operation_attempt = 0
        command.operation_max_attempts = 0
        command.operation_route = None
        command.operation_started_at = None
        command.last_heartbeat_at = None

    @staticmethod
    def _consume_detached_task(task: asyncio.Task) -> None:
        try:
            if not task.cancelled():
                task.exception()
        except (asyncio.CancelledError, Exception):
            pass

    async def _cancel_with_grace(self, task: asyncio.Task) -> None:
        if task.done():
            return
        task.cancel()
        done, _pending = await asyncio.wait(
            {task},
            timeout=self.settings.supervisor_cancellation_grace_seconds,
        )
        if task not in done:
            task.add_done_callback(self._consume_detached_task)

    async def _await_with_heartbeat(
        self,
        awaitable: Awaitable[T],
        *,
        command_id: str,
        timeout_seconds: float,
        heartbeat_message: str,
        heartbeat_phase: str | None = None,
    ) -> T:
        task = asyncio.create_task(awaitable)
        deadline = time.monotonic() + timeout_seconds
        interval = self.settings.supervisor_operation_heartbeat_seconds

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._cancel_with_grace(task)
                    raise TimeoutError(
                        f"İşlem {timeout_seconds:.1f} saniyede tamamlanmadı."
                    )

                done, _pending = await asyncio.wait(
                    {task},
                    timeout=min(interval, remaining),
                )
                if task in done:
                    return task.result()

                command = await self.store.get(command_id)
                self._heartbeat(
                    command,
                    message=heartbeat_message,
                    phase=heartbeat_phase,
                )
                await self.store.put(command)
        finally:
            if not task.done():
                await self._cancel_with_grace(task)

    @staticmethod
    def _decision_key(value: str) -> str:
        translated = (
            value.casefold()
            .replace("ı", "i")
            .replace("ş", "s")
            .replace("ğ", "g")
            .replace("ü", "u")
            .replace("ö", "o")
            .replace("ç", "c")
        )
        normalized = unicodedata.normalize("NFKD", translated)
        ascii_text = "".join(
            char
            for char in normalized
            if not unicodedata.combining(char)
        )
        tokens = re.findall(r"[a-z0-9]+", ascii_text)
        stopwords = {
            "mi", "mı", "mu", "mü", "ve", "veya", "icin", "ile",
            "bir", "bu", "su", "o", "karar", "verilmesi", "gerekiyor",
            "belirlenmelidir", "olup", "olmadigi", "olmadığı",
        }
        return " ".join(token for token in tokens if token not in stopwords)

    @classmethod
    def _decision_similarity(cls, left: str, right: str) -> float:
        a = cls._decision_key(left)
        b = cls._decision_key(right)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.9
        a_tokens = set(a.split())
        b_tokens = set(b.split())
        union = a_tokens | b_tokens
        return len(a_tokens & b_tokens) / len(union) if union else 0.0

    @classmethod
    def _answer_resolves_question(
        cls,
        *,
        question: str,
        answer: str,
    ) -> bool:
        question_key = cls._decision_key(question)
        answer_key = cls._decision_key(answer)

        web_terms = {
            "web", "uygulama", "framework", "vite", "next", "nextjs",
            "fastapi", "flask", "react",
        }
        negative_branch = any(
            phrase in answer_key
            for phrase in (
                "tam web uygulamasina donusturme",
                "web uygulamasina donusturme",
                "framework ekleme",
                "ayri test altyapilari",
                "ayri test altyapisi",
            )
        )
        if negative_branch and web_terms & set(question_key.split()):
            return True

        return False

    def _resolved_decision_memory(
        self,
        command: SupervisorCommand,
    ) -> list[SupervisorDecision]:
        resolved: list[SupervisorDecision] = []
        seen: set[tuple[str, str]] = set()

        for item in [
            *command.decision_history,
            *command.decisions,
        ]:
            if item.status != "answered" or not item.answer:
                continue
            key = (
                self._decision_key(item.question),
                item.answer.strip().casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            resolved.append(item.model_copy(deep=True))

        return resolved

    def _merge_new_decisions(
        self,
        *,
        questions: list[str],
        resolved: list[SupervisorDecision],
    ) -> tuple[list[SupervisorDecision], list[SupervisorDecision]]:
        decisions: list[SupervisorDecision] = []
        auto_resolved: list[SupervisorDecision] = []

        for index, question in enumerate(questions, start=1):
            best: SupervisorDecision | None = None
            best_score = 0.0

            for previous in resolved:
                score = self._decision_similarity(
                    question,
                    previous.question,
                )
                if self._answer_resolves_question(
                    question=question,
                    answer=previous.answer or "",
                ):
                    score = max(score, 0.95)
                if score > best_score:
                    best = previous
                    best_score = score

            if best is not None and best_score >= 0.42:
                decision = SupervisorDecision(
                    id=f"DEC-{index:03d}",
                    question=question,
                    status="answered",
                    answer=best.answer,
                    auto_resolved=True,
                    source_decision_id=best.id,
                )
                decisions.append(decision)
                auto_resolved.append(decision)
            else:
                decisions.append(
                    SupervisorDecision(
                        id=f"DEC-{index:03d}",
                        question=question,
                    )
                )

        return decisions, auto_resolved

    async def _known_paths(self) -> set[str]:
        tree = await self.tools.execute(
            "workspace_list",
            {
                "path": ".",
                "depth": 12,
                "max_entries": 1_000,
            },
        )
        return {
            str(item["path"])
            for item in tree.get("entries", [])
            if item.get("type") == "file" and item.get("path")
        }

    @staticmethod
    def _real_decisions(document: PlanningDocument) -> list[str]:
        decisions = []
        for item in document.critical_decisions:
            normalized = item.strip().casefold()
            if normalized in {"", "yok", "none", "-", "karar yok"}:
                continue
            decisions.append(item.strip())
        return decisions

    @staticmethod
    def _task_from_plan(task: PlanTask) -> SupervisorTask:
        return SupervisorTask(
            id=task.id,
            title=task.title,
            priority=task.priority,
            assigned_agent=task.assigned_agent,
            evidence=[
                evidence.model_dump()
                for evidence in task.evidence
            ],
            acceptance_criteria=task.acceptance_criteria,
            dependencies=task.dependencies,
            dependency_reason=task.dependency_reason,
            parallelizable=task.parallelizable,
            verification=task.verification,
            user_approval=task.user_approval,
            exact_files=task.exact_files,
        )

    @staticmethod
    def _refresh_task_states(command: SupervisorCommand) -> None:
        if any(
            decision.status == "pending"
            for decision in command.decisions
        ):
            command.status = "waiting_decision"
            for task in command.tasks:
                if task.status not in {
                    "completed",
                    "failed",
                    "rework_required",
                    "awaiting_approval",
                    "running",
                    "reviewing",
                }:
                    task.status = "blocked"
            return

        for task in command.tasks:
            if (
                task.status == "failed"
                and any(
                    record.state == "applied"
                    and record.success is not False
                    for record in task.approval_history
                )
            ):
                task.status = "rework_required"
                task.recovery_reason = (
                    task.recovery_reason
                    or "recoverable_applied_evidence"
                )

        completed = {
            task.id
            for task in command.tasks
            if task.status == "completed"
        }
        active = {
            "running",
            "awaiting_approval",
            "reviewing",
        }

        for task in command.tasks:
            if task.status in {
                "completed",
                "failed",
                "rework_required",
                *active,
            }:
                continue
            task.status = (
                "ready"
                if set(task.dependencies) <= completed
                else "blocked"
            )

        if command.tasks and all(
            task.status == "completed"
            for task in command.tasks
        ):
            command.status = "completed"
        elif any(task.status == "awaiting_approval" for task in command.tasks):
            command.status = "awaiting_approval"
        elif any(task.status == "reviewing" for task in command.tasks):
            command.status = "reviewing"
        elif any(task.status == "running" for task in command.tasks):
            command.status = "running"
        elif any(task.status == "ready" for task in command.tasks):
            command.status = "ready"
        elif any(task.status == "rework_required" for task in command.tasks):
            command.status = "ready"
        elif any(task.status == "failed" for task in command.tasks):
            command.status = "failed"
        else:
            command.status = "ready"

    def _planner_prompt(
        self,
        goal: str,
        decision_answers: list[tuple[str, str]] | None = None,
        previous_failure: str | None = None,
    ) -> str:
        decisions = ""
        if decision_answers:
            decisions = "\n\nKullanıcı kararları:\n" + "\n".join(
                f"- {question}: {answer}"
                for question, answer in decision_answers
            )

        failure_guidance = ""
        if previous_failure:
            failure_guidance = f"""
Önceki planlama denemesi reddedildi:
{previous_failure}

Bu hatayı düzelt. Her TASK bloğunda şu alanların tamamını ayrı satırlarda
yaz: Seviye, Atanan Agent, Kanıt, Kabul Kriterleri, Bağımlılıklar,
Bağımlılık Gerekçesi, Paralel Çalışabilir, Doğrulama,
Kullanıcı Onayı ve Kesin Dosyalar.
Markdown tablosu kullanma.
"""

        return f"""Ana hedef:
{goal}
{decisions}
{failure_guidance}

Projeyi gerçek workspace içeriğine göre incele ve yürütülebilir görev
grafiğine dönüştür.

Önemli planlama kuralları:
- AUTO_PROJECT_CONTEXT ile zaten görülen proje yapısını yeniden incelemek
  için bağımsız bir 'proje yapısını incele' görevi oluşturma.
- Teknik olarak bağımsız frontend ve backend görevlerini sırf listede önce
  geldiği için birbirine bağlama.
- 'Çalışır durumda' kabul kriteri kullanıyorsan doğrulama workspace_read
  olamaz; gerçek test/build/compile kanıtı belirt.
- Ürün yönü kullanıcı kararı gerektiriyorsa bunu Kritik Kullanıcı
  Kararları bölümüne yaz ve varsayıma dayalı uygulama görevini zorunlu yapma.
- Her görev tek bir agente atanabilir, ölçülebilir ve kanıtlı olsun.
- Hiçbir dosyayı değiştirme."""

    async def _plan(
        self,
        *,
        command_id: str,
        goal: str,
        routing_mode: str,
        provider: str | None,
        decision_answers: list[tuple[str, str]] | None = None,
    ) -> tuple[AgentResponse, PlanningDocument, list[list[str]]]:
        del routing_mode, provider

        command = await self.store.get(command_id)
        self._set_operation(
            command,
            operation="planning",
            phase="compile_context",
            message=(
                "Planning Compiler proje dosyalarını ve bağlayıcı "
                "kullanıcı kararlarını derliyor."
            ),
            attempt=1,
            max_attempts=1,
            route="deterministic_kernel",
            reset_started_at=True,
        )
        self._event(
            command,
            type="planning_kernel_started",
            message=(
                "Tipli yerel Planning Compiler başlatıldı; "
                "API çağrısı kullanılmıyor."
            ),
            data={"engine": "typed_kernel"},
        )
        await self.store.put(command)

        result = await self.planning_kernel.build(
            goal=goal,
            decision_answers=decision_answers,
        )

        command = await self.store.get(command_id)
        self._heartbeat(
            command,
            phase="validate_graph",
            message=(
                "Derlenen görevler kanıt, agent, kabul kriteri ve "
                "bağımlılık kurallarına göre doğrulanıyor."
            ),
        )
        await self.store.put(command)

        integrity = validate_planning_document(
            result.document,
            known_paths=await self._known_paths(),
            known_agents=set(self.agents.ids()),
        )
        if not integrity.valid:
            raise RuntimeError(
                "Planning Compiler geçersiz görev grafiği üretti: "
                + " | ".join(integrity.errors)
            )

        response = AgentResponse(
            answer=result.text,
            agent_id="planner",
            agent_name="Typed Planning Compiler",
            status="completed",
            steps_used=1,
            model_calls_used=0,
            tools_used=result.tools_used,
            final_route="deterministic_kernel",
            final_provider="local",
            final_model="typed-planning-compiler",
            routing_scores=[],
            trace=[],
        )

        command = await self.store.get(command_id)
        command.operation_route = "deterministic_kernel"
        self._event(
            command,
            type="planning_kernel_completed",
            message=(
                f"Planning Compiler {len(result.document.tasks)} görev "
                f"ve {len(result.document.critical_decisions)} karar "
                "kapısı oluşturdu."
            ),
            data={
                "task_count": len(result.document.tasks),
                "decision_count": len(
                    result.document.critical_decisions
                ),
                "project_types": result.project_types,
                "model_calls": 0,
            },
        )
        await self.store.put(command)

        return (
            response,
            result.document,
            integrity.execution_layers,
        )

    async def _complete_initial_plan(
        self,
        *,
        command_id: str,
        goal: str,
        routing_mode: str,
        provider: str | None,
        auto_start: bool,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        try:
            planner_response, document, layers = await self._plan(
                command_id=command_id,
                goal=goal,
                routing_mode=routing_mode,
                provider=provider,
            )
        except Exception as exc:
            command.status = "failed"
            command.failure_reason = str(exc)
            self._clear_operation(command)
            self._event(
                command,
                type="planning_failed",
                message=str(exc),
            )
            await self.store.put(command)
            return command

        # Persistent stores return detached model instances. Reload the
        # latest command so planning-kernel events/heartbeats are preserved.
        command = await self.store.get(command_id)
        command.failure_reason = None
        if command.status == "failed":
            command.status = "running"
        self._clear_operation(command)
        command.plan_text = planner_response.answer
        command.planning_agent_response = planner_response
        command.execution_layers = layers
        command.tasks = [
            self._task_from_plan(task)
            for task in document.tasks
        ]
        command.decisions = [
            SupervisorDecision(
                id=f"DEC-{index:03d}",
                question=question,
            )
            for index, question in enumerate(
                self._real_decisions(document),
                start=1,
            )
        ]
        self._event(
            command,
            type="plan_accepted",
            message=(
                f"{len(command.tasks)} görevden oluşan plan kabul edildi."
            ),
            data={"execution_layers": layers},
        )
        self._refresh_task_states(command)
        await self.store.put(command)

        if command.autonomy_mode != "locked" and any(d.status == "pending" for d in command.decisions):
            answers = []
            for decision in command.decisions:
                if decision.status == "pending":
                    decision.status = "answered"
                    decision.answer = "Vanilla HTML, CSS ve JavaScript kullan"
                    decision.auto_resolved = True
                    answers.append((decision.id, decision.answer))
            if answers:
                return await self._complete_replan(command_id=command.id, decision_answers=answers)

        if command.auto_run and command.status == "ready":
            return await self.advance(
                command_id=command.id,
                max_tasks=self.settings.supervisor_auto_run_max_tasks,
            )

        return command

    async def create(
        self,
        *,
        goal: str,
        routing_mode: str = "auto",
        provider: str | None = None,
        auto_start: bool = False,
        background: bool = False,
        autonomy_mode: str | None = None,
        force_new: bool = False,
    ) -> SupervisorCommand:
        resolved_autonomy = (
            autonomy_mode
            or self.settings.supervisor_default_autonomy_mode
        )
        if resolved_autonomy not in {"locked", "task", "trusted"}:
            raise ValueError("Geçersiz autonomy mode.")
        ensure_autonomy_mode_allowed(
            self.settings,
            resolved_autonomy,
        )

        def goal_key(value: str) -> str:
            folded = unicodedata.normalize("NFKD", value.casefold())
            folded = "".join(char for char in folded if not unicodedata.combining(char))
            return " ".join(folded.split())

        normalized_goal = goal_key(goal)
        reusable_statuses = {
            "planning",
            "ready",
            "running",
            "awaiting_approval",
            "waiting_decision",
            "rework_required",
        }
        for existing in ([] if force_new else await self.store.list()):
            if (
                not existing.archived
                and
                existing.status in reusable_statuses
                and goal_key(existing.goal) == normalized_goal
            ):
                invalid_pending = False
                for task in existing.tasks:
                    if task.status != "awaiting_approval" or not task.approval_id:
                        continue
                    record = next(
                        (
                            item
                            for item in reversed(task.approval_history)
                            if item.approval_id == task.approval_id
                        ),
                        None,
                    )
                    arguments = record.arguments if record is not None else None
                    if not isinstance(arguments, dict):
                        continue
                    path = str(arguments.get("path") or "")
                    content = str(arguments.get("content") or "")
                    issue = self._static_output_quality_issue(
                        task=task,
                        path=path,
                        content=content,
                    )
                    if issue is None:
                        continue
                    invalid_pending = True
                    if record is not None:
                        record.state = "rejected"
                        record.success = False
                        record.message = issue
                        record.finished_at = utc_now()
                    task.status = "rework_required"
                    task.recovery_reason = "focused_output_quality"
                    self._clear_approval_payload(task, state="rejected", message=issue)
                    self._event(
                        existing,
                        type="stale_pending_output_rejected",
                        task_id=task.id,
                        message=issue,
                    )
                if invalid_pending:
                    self._clear_operation(existing)
                    self._refresh_task_states(existing)
                    await self.store.put(existing)
                    continue
                if auto_start and not existing.auto_run:
                    existing.auto_run = True
                self._event(
                    existing,
                    type="duplicate_submission_reused",
                    message=(
                        "Aynı etkin görev zaten mevcut; yeni ve çakışan bir "
                        "komut oluşturulmadı. Mevcut görev ekrana getirildi."
                    ),
                    data={"requested_background": background},
                )
                await self.store.put(existing)
                if auto_start and existing.status in {"ready", "rework_required"}:
                    self._spawn(
                        self.advance(
                            command_id=existing.id,
                            max_tasks=self.settings.supervisor_auto_run_max_tasks,
                        ),
                        command_id=existing.id,
                        operation="duplicate_resume",
                    )
                return existing

        command = SupervisorCommand(
            id=secrets.token_urlsafe(12),
            goal=goal,
            status="planning",
            autonomy_mode=resolved_autonomy,
            auto_run=auto_start,
            plan_text="",
            tasks=[],
        )
        self._event(
            command,
            type="command_created",
            message=f"Supervisor komutu oluşturuldu. Otonomi: {resolved_autonomy}.",
        )
        self._set_operation(
            command,
            operation="planning",
            phase="queued",
            message="Planner arka plan görevi başlatılıyor.",
            max_attempts=self.settings.supervisor_planner_attempts,
            reset_started_at=True,
        )
        self._event(
            command,
            type="planning_started",
            message="Planner görev grafiğini oluşturuyor.",
        )
        await self.store.put(command)

        if background:
            self._spawn(
                self._complete_initial_plan(
                    command_id=command.id,
                    goal=goal,
                    routing_mode=routing_mode,
                    provider=provider,
                    auto_start=auto_start,
                ),
                command_id=command.id,
                operation="planning",
            )
            return command

        return await self._complete_initial_plan(
            command_id=command.id,
            goal=goal,
            routing_mode=routing_mode,
            provider=provider,
            auto_start=auto_start,
        )

    @staticmethod
    def _seconds_since(value: str | None) -> float | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return (
                datetime.now(timezone.utc) - parsed
            ).total_seconds()
        except (TypeError, ValueError):
            return None

    async def get(self, command_id: str) -> SupervisorCommand:
        command = await self.store.get(command_id)
        age = self._seconds_since(command.last_heartbeat_at)
        if not (
            command.active_operation
            and command.status in {"planning", "running", "reviewing"}
            and age is not None
            and age > self.settings.supervisor_stale_operation_seconds
        ):
            return command

        operation = command.active_operation
        task_id = self._operation_task_id(operation)
        if task_id is not None:
            await self._cancel_background_job(
                command_id=command_id,
                operation=operation,
            )
            command = await self.store.get(command_id)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is not None:
                checkpointed = (
                    operation.startswith(("continuation:", "approval:"))
                    or task.approval_state == "applied"
                    or bool(self._applied_tool_records(task))
                )
                task.status = "rework_required"
                task.recovery_reason = (
                    "task_watchdog_timeout_with_evidence"
                    if checkpointed
                    else "task_watchdog_timeout"
                )
                if checkpointed:
                    task.last_approval_message = (
                        "Arka plan görevi kalp atışı üretmedi. Uygulanmış "
                        "işlem kanıtları korunuyor; Kanıtları Uzlaştır ve "
                        "Devam Et ile yalnızca eksik iş sürdürülecek."
                    )
                else:
                    task.last_approval_message = (
                        "Agent çağrısı kalp atışı üretmedi ve güvenli biçimde "
                        "iptal edildi. Görev yeniden başlatılabilir; bütün "
                        "komut başarısız sayılmadı."
                    )
                task.agent_session_id = None
                task.processing_approval_id = None
                command.failure_reason = None
                self._clear_operation_if(command, operation)
                self._event(
                    command,
                    type="task_watchdog_recovered",
                    task_id=task.id,
                    message=task.last_approval_message,
                    data={
                        "operation": operation,
                        "age_seconds": age,
                        "checkpointed": checkpointed,
                    },
                )
                self._refresh_task_states(command)
                await self.store.put(command)
                return command

        command.status = "failed"
        command.failure_reason = (
            f"{operation} işlemi {age:.0f} saniyedir kalp atışı "
            "üretmedi. Watchdog komutu güvenli biçimde durdurdu."
        )
        self._clear_operation_if(command, operation)
        self._event(
            command,
            type="operation_watchdog_timeout",
            message=command.failure_reason,
            data={"operation": operation, "age_seconds": age},
        )
        await self.store.put(command)
        return command

    async def list(self) -> list[SupervisorCommand]:
        return [
            command for command in await self.store.list()
            if not command.archived
        ]

    async def archive(self, command_id: str) -> SupervisorCommand:
        command = await self.store.get(command_id)
        for (job_command_id, operation), job in list(self._background_jobs.items()):
            if job_command_id == command_id and not job.done():
                await self._cancel_with_grace(job)
        command.archived = True
        command.archived_at = utc_now()
        self._clear_operation(command)
        self._event(
            command,
            type="command_archived",
            message="Görev arşivlendi; aynı istek artık yeni görev olarak oluşturulabilir.",
        )
        await self.store.put(command)
        return command

    async def delete(self, command_id: str) -> bool:
        await self.store.get(command_id)
        for (job_command_id, operation), job in list(self._background_jobs.items()):
            if job_command_id == command_id and not job.done():
                await self._cancel_with_grace(job)
        self._command_locks.pop(command_id, None)
        return await self.store.delete(command_id)

    async def retry_planning(
        self,
        *,
        command_id: str,
        background: bool = True,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        active_or_delivered = any(
            task.attempts > 0
            or task.status in {
                "running",
                "awaiting_approval",
                "reviewing",
                "completed",
            }
            for task in command.tasks
        )
        if active_or_delivered:
            raise ValueError(
                "Çalışmaya başlamış görevler varken plan yeniden "
                "derlenemez."
            )
        if command.status not in {
            "failed",
            "planning",
            "waiting_decision",
            "ready",
        }:
            raise ValueError(
                "Bu komut durumunda plan yeniden derlenemez."
            )

        command.status = "planning"
        command.failure_reason = None
        command.plan_text = ""
        command.tasks = []
        command.decisions = []
        self._set_operation(
            command,
            operation="planning",
            phase="manual_retry",
            message="Planner kullanıcı isteğiyle yeniden başlatılıyor.",
            max_attempts=self.settings.supervisor_planner_attempts,
            reset_started_at=True,
        )
        self._event(
            command,
            type="planning_retry_requested",
            message="Planner manuel olarak yeniden başlatıldı.",
        )
        await self.store.put(command)

        if background:
            self._spawn(
                self._complete_initial_plan(
                    command_id=command.id,
                    goal=command.goal,
                    routing_mode="auto",
                    provider=None,
                    auto_start=command.auto_run,
                ),
                command_id=command.id,
                operation="planning_retry",
            )
            return command

        return await self._complete_initial_plan(
            command_id=command.id,
            goal=command.goal,
            routing_mode="auto",
            provider=None,
            auto_start=command.auto_run,
        )

    async def _complete_replan(
        self,
        *,
        command_id: str,
        decision_answers: list[tuple[str, str]],
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        resolved_memory = self._resolved_decision_memory(command)

        try:
            planner_response, document, layers = await self._plan(
                command_id=command_id,
                goal=command.goal,
                routing_mode="auto",
                provider=None,
                decision_answers=decision_answers,
            )
        except Exception as exc:
            command.status = "failed"
            command.failure_reason = str(exc)
            self._clear_operation(command)
            self._event(
                command,
                type="replanning_failed",
                message=str(exc),
            )
            await self.store.put(command)
            return command

        command.failure_reason = None
        if command.status == "failed":
            command.status = "running"
        self._clear_operation(command)
        command.plan_text = planner_response.answer
        command.planning_agent_response = planner_response
        command.execution_layers = layers
        command.tasks = [
            self._task_from_plan(task)
            for task in document.tasks
        ]

        questions = self._real_decisions(document)
        decisions, auto_resolved = self._merge_new_decisions(
            questions=questions,
            resolved=resolved_memory,
        )
        command.decisions = decisions

        for item in auto_resolved:
            self._event(
                command,
                type="decision_auto_resolved",
                message=(
                    "Planner daha önce yanıtlanan bir kararı tekrar "
                    "üretti; mevcut kullanıcı kararı otomatik uygulandı."
                ),
                data={
                    "question": item.question,
                    "answer": item.answer,
                    "source_decision_id": item.source_decision_id,
                },
            )

        self._event(
            command,
            type="replan_accepted",
            message="Kullanıcı kararlarıyla yeni plan kabul edildi.",
            data={"execution_layers": layers},
        )
        self._refresh_task_states(command)

        if command.status == "ready":
            self._event(
                command,
                type="tasks_unlocked",
                message=(
                    "Karar kapısı tamamlandı; bağımsız görevler "
                    "çalıştırılmaya hazır."
                ),
            )

        await self.store.put(command)
        if command.auto_run and command.status == "ready":
            return await self.advance(
                command_id=command.id,
                max_tasks=self.settings.supervisor_auto_run_max_tasks,
            )
        return command

    async def answer_decision(
        self,
        *,
        command_id: str,
        decision_id: str,
        answer: str,
        replan_when_complete: bool,
        background: bool = False,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        decision = next(
            (
                item
                for item in command.decisions
                if item.id == decision_id
            ),
            None,
        )
        if decision is None:
            raise KeyError("Karar bulunamadı.")

        decision.answer = answer
        decision.status = "answered"
        decision.auto_resolved = False

        history_key = (
            self._decision_key(decision.question),
            answer.strip().casefold(),
        )
        existing_keys = {
            (
                self._decision_key(item.question),
                (item.answer or "").strip().casefold(),
            )
            for item in command.decision_history
        }
        if history_key not in existing_keys:
            command.decision_history.append(
                decision.model_copy(deep=True)
            )

        self._event(
            command,
            type="decision_answered",
            message=f"{decision.id} yanıtlandı ve bağlayıcı karar olarak kaydedildi.",
            data={"question": decision.question, "answer": answer},
        )

        all_answered = (
            command.decisions
            and all(
                item.status == "answered"
                for item in command.decisions
            )
        )

        if replan_when_complete and all_answered:
            command.status = "planning"
            for task in command.tasks:
                if task.status not in {
                    "completed",
                    "failed",
                    "running",
                    "reviewing",
                    "awaiting_approval",
                }:
                    task.status = "blocked"

            self._set_operation(
                command,
                operation="replanning",
                phase="queued",
                message=(
                    "Planner bağlayıcı kullanıcı kararlarıyla "
                    "yeniden planlama kuyruğunda."
                ),
                max_attempts=self.settings.supervisor_planner_attempts,
                reset_started_at=True,
            )
            self._event(
                command,
                type="replanning",
                message=(
                    "Karar kaydedildi; Planner planı bağlayıcı "
                    "kararlara göre yeniden kuruyor."
                ),
            )
            await self.store.put(command)

            answers = [
                (item.question, item.answer or "")
                for item in self._resolved_decision_memory(command)
            ]

            if background:
                self._spawn(
                    self._complete_replan(
                        command_id=command.id,
                        decision_answers=answers,
                    ),
                    command_id=command.id,
                    operation="replanning",
                )
                return command

            return await self._complete_replan(
                command_id=command.id,
                decision_answers=answers,
            )

        self._refresh_task_states(command)
        await self.store.put(command)
        return command

    @staticmethod
    def _execution_ledger(task: SupervisorTask) -> str:
        if not task.approval_history:
            return "Henüz uygulanmış güvenli işlem yok."

        rows: list[str] = []
        for record in sorted(
            task.approval_history,
            key=lambda item: item.version,
        ):
            preview = record.preview or {}
            result = record.result
            target = (
                preview.get("path")
                or preview.get("preset")
                or preview.get("command")
                or "-"
            )
            result_summary = ""
            if isinstance(result, dict):
                if "exit_code" in result:
                    result_summary = (
                        f" exit_code={result.get('exit_code')}"
                        f" success={result.get('success')}"
                    )
                elif "changed" in result:
                    result_summary = (
                        f" changed={result.get('changed')}"
                        f" path={result.get('path')}"
                    )
                elif result.get("error"):
                    result_summary = f" error={result.get('error')}"
            rows.append(
                f"- #{record.version} {record.tool or 'işlem'} "
                f"state={record.state} target={target}{result_summary}"
            )
        return "\n".join(rows)

    @staticmethod
    def _verification_command_matches(
        task: SupervisorTask,
        result: Any,
    ) -> bool:
        if not isinstance(result, dict) or not result.get("success"):
            return False

        expected = task.verification.casefold()
        preset = str(result.get("preset") or "").casefold()
        expected_preset: str | None = None
        if "pytest" in expected:
            expected_preset = "pytest"
        elif "npm test" in expected or "vitest" in expected:
            expected_preset = "npm_test"
        elif "npm" in expected and "build" in expected:
            expected_preset = "npm_build"
        elif "flutter test" in expected:
            expected_preset = "flutter_test"
        elif "flutter analyze" in expected:
            expected_preset = "flutter_analyze"
        elif "gradle" in expected:
            expected_preset = "gradle_test"
        elif "compileall" in expected:
            expected_preset = "python_compile"
        elif "accesssync" in expected and "node" in expected:
            expected_preset = "file_exists"

        # SafeTerminal always returns its preset. Exact preset equality avoids
        # accepting `npm install @testing-library/...` as `npm test` merely
        # because a package name contains the word "test".
        if preset:
            return expected_preset is not None and preset == expected_preset

        command = result.get("command") or []
        if isinstance(command, list):
            tokens = [str(item).casefold() for item in command]
        else:
            tokens = str(command).casefold().split()
        basenames = [Path(item).name for item in tokens]

        if expected_preset == "pytest":
            return any(item == "pytest" for item in basenames)
        if expected_preset == "npm_test":
            return "test" in tokens or any(item == "vitest" for item in basenames)
        if expected_preset == "npm_build":
            return "build" in tokens
        if expected_preset == "flutter_test":
            return "flutter" in basenames and "test" in tokens
        if expected_preset == "flutter_analyze":
            return "flutter" in basenames and "analyze" in tokens
        if expected_preset == "gradle_test":
            return any("gradle" in item for item in basenames) and "test" in tokens
        if expected_preset == "python_compile":
            return "compileall" in tokens
        return result.get("exit_code") == 0

    async def _exact_files_exist(
        self,
        task: SupervisorTask,
    ) -> bool:
        for path in task.exact_files:
            try:
                await self.tools.execute(
                    "workspace_read",
                    {"path": path, "start_line": 1, "end_line": 2},
                )
            except Exception:
                return False
        return True

    async def _synchronize_workspace_evidence(
        self,
        task: SupervisorTask,
    ) -> list[str]:
        """Refresh exact-file evidence from the real workspace.

        A task may start after an earlier interrupted mission already created
        its files. Those files are valid workspace evidence even when this
        command has no workspace_write record.
        """
        existing: list[str] = []
        missing: list[str] = []
        for path in task.exact_files:
            try:
                await self.tools.execute(
                    "workspace_read",
                    {"path": path, "start_line": 1, "end_line": 2},
                )
            except Exception:
                missing.append(path)
            else:
                existing.append(self._normalize_workspace_path(path))

        task.materialized_files = list(dict.fromkeys(existing))
        task.reconciliation_missing_files = missing
        task.workspace_state_validated = not missing
        task.reconciliation_last_checked_at = utc_now()
        return missing

    @staticmethod
    def _command_text(result: Any) -> str:
        if not isinstance(result, dict):
            return ""
        command = result.get("command") or []
        if isinstance(command, list):
            return " ".join(str(item) for item in command)
        return str(command)

    @staticmethod
    def _applied_tool_fingerprints(
        task: SupervisorTask,
    ) -> list[str]:
        fingerprints: list[str] = []
        for record in task.approval_history:
            if record.state != "applied" or record.success is False:
                continue
            fingerprint = record.fingerprint
            if (
                fingerprint is None
                and record.tool
                and record.arguments is not None
            ):
                fingerprint = tool_fingerprint(
                    record.tool,
                    record.arguments,
                )
            if fingerprint:
                fingerprints.append(fingerprint)
        return list(dict.fromkeys(fingerprints))

    @staticmethod
    def _applied_tool_records(
        task: SupervisorTask,
    ) -> list[SupervisorApprovalRecord]:
        return [
            record
            for record in task.approval_history
            if record.state == "applied"
            and record.success is not False
            and record.tool
        ]

    def _reconcile_focused_generation_revision(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> bool:
        previous = task.focused_generation_revision
        if previous == FOCUSED_GENERATION_REVISION:
            return False
        task.focused_generation_revision = FOCUSED_GENERATION_REVISION
        protocol_related = (
            task.recovery_reason in {
                "focused_step_failed",
                "focused_step_failed",
                "focused_protocol_failed",
                "focused_step_incomplete",
            }
            or "protokol" in (task.last_answer or "").casefold()
            or "protokol" in (task.last_approval_message or "").casefold()
        )
        if protocol_related:
            task.blocked_reason = None
            task.blocked_state_token = None
            task.recovery_reason = None
            task.local_model_attempts = 0
            task.last_approval_message = (
                "Dosya üretim protokolü yükseltildi; eski kesilmiş JSON "
                "cevapları geçersiz kılındı."
            )
            if task.status in {"rework_required", "failed"}:
                task.status = "running"
        self._event(
            command,
            type="focused_generation_revision_advanced",
            task_id=task.id,
            message=(
                "Tek dosya üretim protokolü ham kaynak zarfına yükseltildi. "
                "JSON içine uzun kaynak kodu gömme ve kesilme döngüsü kapatıldı."
            ),
            data={
                "previous": previous or "legacy-json",
                "current": FOCUSED_GENERATION_REVISION,
                "protocol_state_reset": protocol_related,
            },
        )
        return True

    def _current_terminal_runtime_revision(self) -> str:
        terminal = self.tools.get("safe_terminal")
        return str(
            getattr(
                terminal,
                "runtime_revision",
                TERMINAL_RUNTIME_REVISION,
            )
        )

    @staticmethod
    def _result_runtime_revision(
        record: SupervisorApprovalRecord,
    ) -> str | None:
        if isinstance(record.result, dict):
            value = record.result.get("runtime_revision")
            if value:
                return str(value)
        return None

    def _task_state_token(self, task: SupervisorTask) -> str:
        payload = {
            "last_write": self._latest_changed_write_version(task),
            "last_environment_change": (
                self._latest_successful_environment_change_version(task)
            ),
            "runtime_revision": self._current_terminal_runtime_revision(),
            "approval_version": task.approval_version,
            "materialized_files": sorted(task.materialized_files),
            "successful_verification": task.successful_verification_version,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()

    def _mark_task_blocked(
        self,
        *,
        task: SupervisorTask,
        recovery_reason: str,
        message: str,
    ) -> None:
        task.status = "rework_required"
        task.recovery_reason = recovery_reason
        task.blocked_reason = message
        task.last_approval_message = message
        task.blocked_state_token = self._task_state_token(task)

    @staticmethod
    def _is_mission_budget_error(exc: Exception) -> bool:
        message = str(exc).casefold()
        return (
            "misyon model çağrısı bütçesi tükendi" in message
            or "misyon tahmini giriş token bütçesi tükendi" in message
        )

    @staticmethod
    def _is_route_unavailable_error(exc: Exception) -> bool:
        message = str(exc).casefold()
        return (
            "uygun model rotası bulunamadı" in message
            or "no eligible model route" in message
            or "no model route available" in message
        )

    @staticmethod
    def _is_transient_focused_error(exc: Exception) -> bool:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return True
        message = str(exc).casefold()
        transient_markers = (
            "hiçbir model rotasından cevap alınamadı",
            "bütün aday model rotaları başarısız oldu",
            "timed out",
            "timeout",
            "zaman aş",
            "temporarily unavailable",
            "temporary failure",
            "connection reset",
            "connection aborted",
            "connection refused",
            "service unavailable",
            "provider call",
            "provider çağrısı",
        )
        return any(marker in message for marker in transient_markers)

    @staticmethod
    def _mission_budget_block_message(exc: Exception) -> str:
        return (
            "Ücretsiz misyon bütçesi doldu. Prometheus yeni API çağrısı yapmadı "
            "ve ücretli rotaya geçmedi. Mevcut workspace ve kanıtlar "
            f"korundu. Ayrıntı: {exc}"
        )

    def _reconcile_terminal_runtime_revision(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> bool:
        current = self._current_terminal_runtime_revision()
        previous = task.terminal_runtime_revision
        if previous == current:
            return False

        task.terminal_runtime_revision = current
        stale_toolchain_failure = any(
            item.kind in {
                "missing_node_toolchain",
                "npm_dependencies_not_installed",
                "npm_install_failed",
                "npm_child_node_path_missing",
                "npm_test_packages_missing",
                "vitest_globals_required",
                "vitest_global_api_missing",
                "missing_frontend_test_package",
                "missing_command",
            }
            for item in task.failure_history
        ) or task.recovery_reason in {
            "repeated_failure_blocked",
            "external_prerequisite_blocked",
        }

        if stale_toolchain_failure:
            task.failure_counts = {}
            task.failure_state_tokens = {}
            task.failure_history = []
            task.verification_failures = 0
            task.blocked_reason = None
            task.blocked_state_token = None
            task.recovery_reason = None
            task.attempted_strategies = [
                item
                for item in task.attempted_strategies
                if item not in {
                    "install_node_lts",
                    "npm_install",
                    "npm_install_repaired_path",
                }
            ]
            self._event(
                command,
                type="terminal_runtime_revision_advanced",
                task_id=task.id,
                message=(
                    "Prometheus terminal çalışma ortamı güncellendi. Eski PATH/"
                    "araç-zinciri hata kayıtları geçersiz kılındı; görev "
                    "yalnızca bir kez yeni runtime ile devam edecek."
                ),
                data={
                    "previous_revision": previous or "legacy",
                    "current_revision": current,
                },
            )
            return True
        return previous is not None

    @staticmethod
    def _environment_changing_preset(
        record: SupervisorApprovalRecord,
    ) -> str | None:
        if (
            record.tool != "safe_terminal"
            or record.state != "applied"
            or record.success is not True
            or not isinstance(record.arguments, dict)
        ):
            return None
        preset = str(record.arguments.get("preset", "")).strip()
        if preset in {
            "install_node_lts",
            "npm_install",
            "npm_install_dev",
            "pip_install_dev",
        }:
            return preset
        return None

    @classmethod
    def _latest_successful_environment_change_version(
        cls,
        task: SupervisorTask,
    ) -> int:
        versions = [
            record.version
            for record in task.approval_history
            if cls._environment_changing_preset(record) is not None
        ]
        return max(versions, default=0)

    def _reconcile_environment_revision(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> bool:
        latest = self._latest_successful_environment_change_version(task)
        if latest <= task.last_environment_change_version:
            return False

        changed_records = [
            record
            for record in task.approval_history
            if record.version > task.last_environment_change_version
            and record.version <= latest
            and self._environment_changing_preset(record) is not None
        ]
        presets = [
            self._environment_changing_preset(record)
            for record in changed_records
        ]
        presets = [preset for preset in presets if preset is not None]

        task.last_environment_change_version = latest
        task.environment_revision += 1

        # A successful toolchain/dependency installation changes the
        # verification environment. Old missing-command/dependency
        # signatures are no longer authoritative.
        task.failure_counts = {}
        task.failure_state_tokens = {}
        task.failure_history = []
        task.verification_failures = 0
        task.blocked_reason = None
        task.blocked_state_token = None
        if task.recovery_reason in {
            "repeated_failure_blocked",
            "external_prerequisite_blocked",
            "background_operation_interrupted",
        }:
            task.recovery_reason = None

        self._event(
            command,
            type="environment_revision_advanced",
            task_id=task.id,
            message=(
                "Araç zinciri veya bağımlılık ortamı değişti. "
                "Kurulumdan önceki terminal hata kayıtları geçersiz "
                "kılındı ve doğrulama yeni ortamda bir kez yeniden "
                "çalıştırılacak."
            ),
            data={
                "environment_revision": task.environment_revision,
                "approval_version": latest,
                "presets": presets,
            },
        )
        return True

    @staticmethod
    def _latest_changed_write_version(
        task: SupervisorTask,
    ) -> int:
        versions = [
            record.version
            for record in task.approval_history
            if record.tool == "workspace_write"
            and record.state == "applied"
            and record.success is not False
            and isinstance(record.result, dict)
            and record.result.get("changed") is True
        ]
        return max(versions, default=0)

    def _latest_successful_verification(
        self,
        task: SupervisorTask,
    ) -> SupervisorApprovalRecord | None:
        last_write = self._latest_changed_write_version(task)
        return next(
            (
                record
                for record in reversed(task.approval_history)
                if record.tool == "safe_terminal"
                and record.state == "applied"
                and record.success is True
                and record.version > last_write
                and self._verification_command_matches(
                    task,
                    record.result,
                )
            ),
            None,
        )

    async def _missing_exact_files(
        self,
        task: SupervisorTask,
    ) -> list[str]:
        missing: list[str] = []
        for path in task.exact_files:
            try:
                await self.tools.execute(
                    "workspace_read",
                    {
                        "path": path,
                        "start_line": 1,
                        "end_line": 2,
                    },
                )
            except Exception:
                missing.append(path)
        return missing

    async def _reconcile_task_evidence(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        reason: str,
    ) -> bool:
        """
        Reconcile the execution ledger before another model call.

        Returns True when the task was completed locally.
        """
        missing = await self._synchronize_workspace_evidence(task)
        verification = self._latest_successful_verification(task)

        task.reconciliation_verification_found = (
            verification is not None
        )

        if not missing and verification is not None:
            completion = await self._local_completion_response(
                task=task,
                tool_name="safe_terminal",
                result=verification.result,
            )
            if completion is not None:
                task.recovery_reason = None
                task.status = "running"
                self._event(
                    command,
                    type="task_evidence_reconciled",
                    task_id=task.id,
                    message=(
                        f"{task.id} için kesin dosyalar ve başarılı "
                        "doğrulama kanıtı yerel olarak uzlaştırıldı."
                    ),
                    data={
                        "reason": reason,
                        "verification_version": verification.version,
                    },
                )
                await self._handle_worker_response(
                    command=command,
                    task=task,
                    response=completion,
                )
                return True

        details: list[str] = []
        if missing:
            details.append(
                "Eksik kesin dosyalar: " + ", ".join(missing)
            )
        if verification is None:
            details.append(
                "Son gerçek dosya değişikliğinden sonra başarılı "
                "doğrulama kanıtı bulunmuyor."
            )

        task.status = "rework_required"
        task.recovery_reason = "evidence_incomplete"
        task.last_approval_message = (
            "Kanıt uzlaştırması tamamlanamadı. "
            + " ".join(details)
        )
        self._event(
            command,
            type="task_evidence_incomplete",
            task_id=task.id,
            message=task.last_approval_message,
            data={
                "reason": reason,
                "missing_files": missing,
                "verification_found": verification is not None,
            },
        )
        return False

    @staticmethod
    def _supervisor_session_id(
        command_id: str,
        task_id: str,
    ) -> str:
        return f"supervisor:{command_id}:{task_id}"

    @staticmethod
    def _is_supervisor_session(session_id: str) -> bool:
        return session_id.startswith("supervisor:")

    @staticmethod
    def _normalize_workspace_path(path: str) -> str:
        return path.replace("\\", "/").lstrip("./")

    @classmethod
    def _record_materialized_file(
        cls,
        task: SupervisorTask,
        path: str | None,
    ) -> None:
        if not path:
            return
        normalized = cls._normalize_workspace_path(path)
        current = {
            cls._normalize_workspace_path(item)
            for item in task.materialized_files
        }
        if normalized not in current:
            task.materialized_files.append(normalized)

    @classmethod
    def _applied_write_paths(
        cls,
        task: SupervisorTask,
    ) -> set[str]:
        paths = {
            cls._normalize_workspace_path(item)
            for item in task.materialized_files
        }
        for record in task.approval_history:
            if (
                record.tool not in {"workspace_write", "write_file", "single_file_action"}
                or record.state != "applied"
                or record.success is False
            ):
                continue
            result = record.result
            arguments = record.arguments
            path = None
            if isinstance(result, dict):
                path = result.get("path") or result.get("target_file") or result.get("file")
            if not path and isinstance(arguments, dict):
                path = arguments.get("path") or arguments.get("target_file") or arguments.get("file")
            if path:
                paths.add(cls._normalize_workspace_path(str(path)))
        return paths

    @staticmethod
    def _has_applied_workspace_write(task: SupervisorTask) -> bool:
        return any(
            record.tool in {
                "workspace_write",
                "write_file",
                "single_file_action",
            }
            and record.state == "applied"
            and record.success is not False
            for record in task.approval_history
        )

    def _workspace_file_is_materialized(self, path: str) -> bool:
        try:
            candidate = self.workspace.resolve(path, must_exist=True)
            return candidate.is_file() and candidate.stat().st_size > 0
        except (ToolError, OSError):
            return False

    def _next_unmaterialized_file(
        self,
        task: SupervisorTask,
    ) -> str | None:
        materialized = self._applied_write_paths(task)
        for path in task.exact_files:
            normalized = self._normalize_workspace_path(path)
            if normalized in materialized:
                continue
            if self._workspace_file_is_materialized(path):
                continue
            return path
        return None

    @staticmethod
    def _verification_arguments(
        task: SupervisorTask,
    ) -> dict[str, Any] | None:
        try:
            tokens = shlex.split(task.verification)
        except ValueError:
            return None
        lowered = [token.casefold() for token in tokens]

        if "pytest" in lowered:
            pytest_index = lowered.index("pytest")
            selectors: list[str] = []
            for token in tokens[pytest_index + 1 :]:
                lowered_token = token.casefold()
                if lowered_token in {"-q", "--quiet"}:
                    continue
                if token.startswith("-"):
                    return None
                normalized = token.replace("\\", "/")
                selector_path = normalized.split("::", 1)[0]
                selector = PurePosixPath(selector_path)
                if (
                    selector.is_absolute()
                    or ".." in selector.parts
                    or not selector_path.casefold().endswith(".py")
                ):
                    return None
                if normalized not in selectors:
                    selectors.append(normalized)
            return {"preset": "pytest", "extra_args": selectors}
        if lowered and lowered[0] == "node":
            if "-e" in lowered and "accesssync" in task.verification.casefold():
                quoted_paths = re.findall(
                    r"accessSync\(\s*['\"]([^'\"]+)['\"]\s*\)",
                    task.verification,
                    flags=re.IGNORECASE,
                )
                paths = quoted_paths or list(task.exact_files)
                return {"preset": "file_exists", "extra_args": paths}
            if "--test" in lowered or (len(lowered) >= 2 and lowered[1] == "test"):
                extra = [t for t in tokens if t.casefold() not in {"node", "--test", "test"}]
                if not extra:
                    extra = [
                        path
                        for path in task.exact_files
                        if Path(path).suffix.casefold() in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
                    ]
                return {"preset": "node_test", "extra_args": extra}
            return {"preset": "node_check", "extra_args": [t for t in tokens if t.casefold() != "node"]}
        if len(lowered) >= 2 and lowered[:2] == ["npm", "test"]:
            extra: list[str] = []
            if "--" in tokens:
                separator = tokens.index("--")
                extra = tokens[separator + 1 :]
            if not extra:
                extra = [
                    path
                    for path in task.exact_files
                    if (
                        Path(path).suffix.casefold()
                        in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
                        and (
                            any(
                                part.casefold() in {"test", "tests", "__tests__"}
                                for part in PurePosixPath(
                                    path.replace("\\", "/")
                                ).parts[:-1]
                            )
                            or re.search(
                                r"(?:^|[._-])(?:test|spec)(?:[._-]|$)",
                                Path(path).name,
                                flags=re.IGNORECASE,
                            )
                        )
                    )
                ]
            return {"preset": "npm_test", "extra_args": extra}
        if lowered[:2] == ["flutter", "test"]:
            return {"preset": "flutter_test", "extra_args": []}
        if lowered[:2] == ["flutter", "analyze"]:
            return {"preset": "flutter_analyze", "extra_args": []}
        if "compileall" in lowered:
            return {"preset": "python_compile", "extra_args": []}
        if lowered[-2:] == ["gradlew", "test"] or (
            lowered and lowered[-1] == "test"
            and any("gradlew" in token for token in lowered)
        ):
            return {"preset": "gradle_test", "extra_args": []}
        return None

    @staticmethod
    def _effective_tool_success(
        tool_name: str,
        application_success: bool,
        result: Any,
    ) -> bool:
        if not application_success:
            return False
        if (
            tool_name == "safe_terminal"
            and isinstance(result, dict)
            and "success" in result
        ):
            return bool(result.get("success"))
        return True

    def _auto_execution_allowed(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        if self.tools.is_high_risk(tool_name, arguments):
            return False
        if command.autonomy_mode == "trusted":
            return trusted_autonomy_enabled(self.settings)
        if command.autonomy_mode == "task" and task.autonomy_granted:
            return True
        return False

    def _record_verification_failure(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        result: dict[str, Any],
    ):
        diagnosis = classify_verification_failure(
            result=result,
            verification=task.verification,
        )
        repair_state_payload = {
            "last_write": self._latest_changed_write_version(task),
            "last_environment_change": (
                self._latest_successful_environment_change_version(task)
            ),
            "runtime_revision": self._current_terminal_runtime_revision(),
            "materialized_files": sorted(task.materialized_files),
        }
        repair_state = hashlib.sha256(
            json.dumps(
                repair_state_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        previous_repair_state = task.failure_state_tokens.get(
            diagnosis.signature
        )
        repair_state_changed = (
            previous_repair_state is not None
            and previous_repair_state != repair_state
        )
        task.failure_state_tokens[diagnosis.signature] = repair_state
        count = task.failure_counts.get(diagnosis.signature, 0) + 1
        task.failure_counts[diagnosis.signature] = count
        task.failure_history.append(
            SupervisorFailureRecord(
                signature=diagnosis.signature,
                kind=diagnosis.kind,
                summary=diagnosis.summary,
                count=count,
                strategy_key=diagnosis.strategy_key,
                exit_code=(
                    result.get("exit_code")
                    if isinstance(result.get("exit_code"), int)
                    else None
                ),
            )
        )
        self._event(
            command,
            type="verification_failure_classified",
            task_id=task.id,
            message=(
                f"{diagnosis.kind}: {diagnosis.summary} "
                f"(aynı imza {count}. kez)"
            ),
            data={
                "signature": diagnosis.signature,
                "kind": diagnosis.kind,
                "count": count,
                "strategy_key": diagnosis.strategy_key,
                "repair_state_changed": repair_state_changed,
            },
        )
        return diagnosis, count, repair_state_changed

    @staticmethod
    def _should_block_repeated_failure(
        *,
        count: int,
        limit: int,
        repair_state_changed: bool,
    ) -> bool:
        return (
            count >= limit
            and (
                not repair_state_changed
                or count > limit
            )
        )

    async def _set_supervisor_pending_approval(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
    ) -> tuple[bool, Any | None]:
        fingerprint = tool_fingerprint(tool_name, arguments)
        previous = next(
            (
                record
                for record in reversed(task.approval_history)
                if record.state == "applied"
                and record.fingerprint == fingerprint
            ),
            None,
        )
        if previous is not None:
            if previous.success is True:
                self._event(
                    command,
                    type="successful_tool_evidence_reused",
                    task_id=task.id,
                    message=(
                        f"{tool_name} daha önce başarıyla uygulandı; "
                        "aynı işlem yeniden çalıştırılmadı."
                    ),
                    data={
                        "approval_version": previous.version,
                        "fingerprint": fingerprint,
                    },
                )
                return False, previous.result

            if (
                tool_name == "safe_terminal"
                and self._latest_changed_write_version(task)
                <= previous.version
                and self._latest_successful_environment_change_version(task)
                <= previous.version
                and self._result_runtime_revision(previous)
                == self._current_terminal_runtime_revision()
            ):
                blocked = {
                    "success": False,
                    "duplicate_blocked": True,
                    "original_result": previous.result,
                    "reason": (
                        "Aynı başarısız doğrulama komutu, sonrasında dosya "
                        "değişikliği olmadığı için tekrar çalıştırılmadı."
                    ),
                }
                self._event(
                    command,
                    type="duplicate_verification_blocked",
                    task_id=task.id,
                    message=blocked["reason"],
                    data={
                        "approval_version": previous.version,
                        "fingerprint": fingerprint,
                    },
                )
                return False, blocked

        if self._auto_execution_allowed(
            command=command,
            task=task,
            tool_name=tool_name,
            arguments=arguments,
        ):
            task.approval_version += 1
            synthetic_id = (
                f"auto-{task.id.lower()}-{task.approval_version}"
            )
            result = await self.tools.execute_direct(tool_name, arguments)
            effective_success = self._effective_tool_success(
                tool_name,
                True,
                result,
            )
            self._upsert_approval_record(
                task,
                approval_id=synthetic_id,
                approval_version=task.approval_version,
                phase="worker",
                state="applied",
                tool=tool_name,
                description=(
                    "Görev kapsamı daha önce onaylandığı için otomatik "
                    "uygulandı."
                ),
                preview=None,
                arguments=arguments,
                fingerprint=fingerprint,
                message=reason,
                started_at=utc_now(),
                finished_at=utc_now(),
                success=effective_success,
                result=result,
            )
            if tool_name == "workspace_write" and isinstance(result, dict):
                self._record_materialized_file(task, result.get("path"))
            self._event(
                command,
                type="scoped_tool_auto_applied",
                task_id=task.id,
                message=(
                    f"{tool_name}, {command.autonomy_mode} otonomi "
                    "kapsamında ek onay istenmeden uygulandı."
                ),
                data={
                    "approval_version": task.approval_version,
                    "tool": tool_name,
                    "effective_success": effective_success,
                },
            )
            return False, result

        try:
            result = await self.tools.execute(tool_name, arguments)
        except ToolApprovalRequired as exc:
            pending = exc.pending
        else:
            if tool_name == "workspace_write" and isinstance(result, dict):
                self._record_materialized_file(task, result.get("path"))
            self._event(
                command,
                type="supervisor_tool_noop",
                task_id=task.id,
                message=f"{tool_name} yeni onay gerektirmedi.",
                data={"result": result},
            )
            return False, result

        task.status = "awaiting_approval"
        task.agent_session_id = self._supervisor_session_id(
            command.id,
            task.id,
        )
        task.approval_id = pending.id
        task.approval_phase = "worker"
        task.approval_version += 1
        task.approval_state = "pending"
        task.approval_tool = pending.tool_name
        task.approval_description = pending.description
        task.approval_preview = pending.preview
        task.approval_expires_at = pending.expires_at.isoformat()
        task.processing_approval_id = None
        task.last_approval_message = reason

        self._upsert_approval_record(
            task,
            approval_id=pending.id,
            approval_version=task.approval_version,
            phase="worker",
            state="pending",
            tool=pending.tool_name,
            description=pending.description,
            preview=pending.preview,
            arguments=pending.arguments,
            fingerprint=tool_fingerprint(
                pending.tool_name,
                pending.arguments,
            ),
            message=reason,
        )
        command.status = "awaiting_approval"
        self._set_operation(
            command,
            operation=f"approval:{task.id}",
            phase="waiting_for_user",
            message=reason,
            attempt=task.approval_version,
            route="autonomous_repair_runtime",
            reset_started_at=True,
        )
        self._event(
            command,
            type="task_approval_required",
            task_id=task.id,
            message=(
                f"{task.id} güvenli işlem "
                f"{task.approval_version} için kullanıcı onayı bekliyor."
            ),
            data={
                "approval_id": pending.id,
                "approval_version": task.approval_version,
                "tool": pending.tool_name,
                "source": "autonomous_repair_runtime",
                "autonomy_mode": command.autonomy_mode,
            },
        )
        return True, None

    @staticmethod
    def _focused_path_score(target_path: str, candidate_path: str) -> int:
        target = Path(target_path)
        candidate = Path(candidate_path)
        target_name = target.name.casefold()
        candidate_name = candidate.name.casefold()
        target_stem = re.sub(
            r"\.(?:test|spec)$",
            "",
            target.stem.casefold(),
        )
        candidate_stem = re.sub(
            r"\.(?:test|spec)$",
            "",
            candidate.stem.casefold(),
        )
        target_suffix = target.suffix.casefold()
        candidate_suffix = candidate.suffix.casefold()

        score = 0
        if candidate_name in {
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "pubspec.yaml",
            "cargo.toml",
        }:
            score += 40
        if target_stem and target_stem == candidate_stem:
            score += 120
        if target.parent == candidate.parent:
            score += 45
        if (
            target_suffix in {".js", ".ts", ".jsx", ".tsx", ".py"}
            and candidate_suffix in {".js", ".ts", ".jsx", ".tsx", ".py"}
            and target.parent == candidate.parent
        ):
            score += 35
        if {
            target_suffix,
            candidate_suffix,
        } == {".html", ".css"}:
            score += 90
        if target_suffix == ".html" and candidate_suffix in {
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
        }:
            score += 70
        if (
            target_suffix in {".js", ".ts", ".jsx", ".tsx"}
            and candidate_suffix == ".html"
            and "test" not in target_name
            and "tests" not in {
                part.casefold() for part in target.parts
            }
        ):
            score += 65
        if "test" in target_name and target_stem in candidate_stem:
            score += 80
        return score

    @staticmethod
    def _focused_context_clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        marker = "\n... dosya bağlamı kırpıldı ...\n"
        available = max(2, limit - len(marker))
        head = int(available * 0.7)
        return text[:head] + marker + text[-(available - head) :]

    def _raw_workspace_text(self, path: str) -> str | None:
        """Read one safe UTF-8 file through the central workspace policy."""

        try:
            candidate = self.workspace.resolve(path, must_exist=True)
            self.workspace.ensure_text_file(candidate)
            return candidate.read_text(encoding="utf-8")
        except (ToolError, OSError, UnicodeError):
            return None

    @classmethod
    def _verification_context_paths(
        cls,
        task: SupervisorTask,
    ) -> list[str]:
        try:
            tokens = shlex.split(task.verification)
        except ValueError:
            return []
        supported_suffixes = (
            ".py",
            ".js",
            ".mjs",
            ".cjs",
            ".ts",
            ".tsx",
            ".jsx",
            ".json",
        )
        paths: list[str] = []
        for token in tokens:
            raw = token.replace("\\", "/")
            raw_path = PurePosixPath(raw)
            if (
                raw.startswith("-")
                or raw_path.is_absolute()
                or ".." in raw_path.parts
            ):
                continue
            normalized = cls._normalize_workspace_path(raw)
            if (
                not normalized
                or not normalized.casefold().endswith(supported_suffixes)
            ):
                continue
            paths.append(normalized)
        return list(dict.fromkeys(paths))

    @classmethod
    def _local_import_context_paths(
        cls,
        *,
        source_path: str,
        content: str,
    ) -> list[str]:
        if not source_path.casefold().endswith(
            (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")
        ):
            return []
        references = re.findall(
            r"""(?:from\s+|import\s*\(|require\s*\()\s*
            ["'](?P<path>\.{1,2}/[^"']+)["']""",
            content,
            flags=re.VERBOSE,
        )
        parent = posixpath.dirname(
            cls._normalize_workspace_path(source_path)
        )
        resolved: list[str] = []
        for reference in references:
            candidate = posixpath.normpath(
                posixpath.join(parent, reference)
            )
            if candidate == ".." or candidate.startswith("../"):
                continue
            resolved.append(cls._normalize_workspace_path(candidate))
        return list(dict.fromkeys(resolved))

    async def _compile_focused_context(
        self,
        *,
        task: SupervisorTask,
        task_text: str,
        target_path: str,
        snapshots: dict[str, tuple[dict[str, Any], FileMemory]],
        full_paths: list[str],
        summary_paths: list[str],
        direct_related: set[str],
        graph_related: set[str],
        missing: list[str],
        full_budget: int,
        baseline_context: str,
        include_hypotheses: bool,
    ) -> str | None:
        """Measure a capsule and return it only when active mode is safe."""

        if (
            self.settings.context_compiler_mode == "off"
            or not self.settings.project_memory_enabled
        ):
            return None

        try:
            verification_paths = set(
                self._verification_context_paths(task)
            )
            evidence_paths = {
                self._normalize_workspace_path(
                    str(item.get("value") or "")
                )
                for item in task.evidence
                if item.get("type") == "file" and item.get("value")
            }
            retrieved_cards = []
            if self.settings.context_rag_enabled:
                retrieved_cards = (
                    await self.project_memory.retrieve_context_cards(
                        query=task_text,
                        seed_paths=list(
                            dict.fromkeys(
                                [
                                    target_path,
                                    *sorted(direct_related),
                                    *sorted(graph_related),
                                    *snapshots.keys(),
                                ]
                            )
                        ),
                        include_hypotheses=include_hypotheses,
                        limit=self.settings.context_rag_max_cards,
                        scan_limit=self.settings.context_rag_scan_limit,
                    )
                )
                retrieved_cards = [
                    card
                    for card in retrieved_cards
                    if card.evidence_type != "file"
                ]
            rag_capsule = self.attention_broker.build_capsule(
                task_text=task_text,
                target_path=target_path,
                cards=[
                    card
                    for card in retrieved_cards
                    if card.source_path not in set(full_paths)
                ],
                max_chars=(
                    self.settings.project_memory_attention_budget_chars
                ),
            )
            selected_rag_cards = {
                card.id: card for card in retrieved_cards
            }
            compact_rag_lines = []
            for card_id in rag_capsule.selected_card_ids:
                card = selected_rag_cards.get(card_id)
                if card is None:
                    continue
                state = "H" if card.state == "hypothesis" else "V"
                source = (
                    f" @{card.source_path}"
                    if card.source_path
                    and card.source_path not in card.claim
                    else ""
                )
                compact_rag_lines.append(
                    f"- {state} {card.claim}{source}"
                )
            compact_rag_text = (
                "RAG_V1 | V=verified; H=untrusted hypothesis\n"
                + "\n".join(compact_rag_lines)
            )

            segments: list[ContextSegment] = []
            if compact_rag_lines:
                segments.append(
                    ContextSegment(
                        id="retrieved-evidence",
                        layer="L1",
                        text=compact_rag_text,
                        priority=95,
                    )
                )

            if target_path not in snapshots:
                segments.append(
                    ContextSegment(
                        id="target-state",
                        layer="L2",
                        text=(
                            f"{target_path} does not exist yet and will be "
                            "created by this task."
                        ),
                        priority=100,
                        required=True,
                        source_path=target_path,
                    )
                )

            for path in full_paths:
                result, memory = snapshots[path]
                required = (
                    path == target_path
                    or path in direct_related
                    or path in verification_paths
                    or path in evidence_paths
                )
                segments.append(
                    ContextSegment(
                        id=f"source:{path}",
                        layer="L2" if required else "L3",
                        text=self._focused_context_clip(
                            str(result.get("content") or ""),
                            full_budget,
                        ),
                        priority=100 if path == target_path else 85,
                        required=required,
                        source_path=path,
                        source_sha256=memory.sha256,
                    )
                )

            for path in summary_paths:
                _result, memory = snapshots[path]
                segments.append(
                    ContextSegment(
                        id=f"outline:{path}",
                        layer="L3",
                        text=memory.outline,
                        priority=50,
                        source_path=path,
                        source_sha256=memory.sha256,
                    )
                )

            evidence_gaps = [
                path for path in missing if path != target_path
            ]
            compilation = self.context_compiler.compile(
                task_text=task_text,
                segments=segments,
                max_chars=min(
                    self.settings.context_compiler_shadow_budget_chars,
                    self.settings.supervisor_focused_context_max_chars,
                ),
                baseline_chars=len(baseline_context),
                missing_evidence=evidence_gaps,
            )
            await self.project_memory.record_context_compilation(
                source="supervisor_focused",
                task_text=f"{task.id}:{task.title}:{target_path}",
                mode=self.settings.context_compiler_mode,
                cache_key=compilation.cache_key,
                baseline_chars=compilation.baseline_chars,
                candidate_chars=compilation.chars,
                baseline_estimated_tokens=(
                    compilation.baseline_estimated_tokens
                ),
                candidate_estimated_tokens=compilation.estimated_tokens,
                saved_chars=compilation.saved_chars,
                eligible=compilation.eligible,
                fallback_required=compilation.fallback_required,
                selected_segment_ids=compilation.selected_segment_ids,
                omitted_segment_ids=compilation.omitted_segment_ids,
                deduplicated_segment_ids=(
                    compilation.deduplicated_segment_ids
                ),
                source_hashes=compilation.source_hashes,
                retrieved_card_ids=rag_capsule.selected_card_ids,
                missing_evidence=compilation.missing_evidence,
            )
            if (
                self.settings.context_compiler_mode == "active"
                and compilation.eligible
                and compilation.chars < compilation.baseline_chars
            ):
                return compilation.text
        except Exception:
            # Context optimization must never block a real task. Any compiler
            # failure falls back to the already-built full evidence context.
            return None
        return None

    async def _focused_context(
        self,
        task: SupervisorTask,
        *,
        target_path: str,
    ) -> str:
        snapshots: dict[str, tuple[dict[str, Any], FileMemory]] = {}
        missing: list[str] = []

        verification_context_paths = self._verification_context_paths(task)
        evidence_context_paths = [
            self._normalize_workspace_path(
                str(item.get("value") or "")
            )
            for item in task.evidence
            if item.get("type") == "file" and item.get("value")
        ]
        candidate_paths = list(
            dict.fromkeys(
                [
                    *task.exact_files,
                    *verification_context_paths,
                    *evidence_context_paths,
                ]
            )
        )
        for path in candidate_paths:
            try:
                result = await self.tools.execute(
                    "workspace_read",
                    {
                        "path": path,
                        "start_line": 1,
                        "end_line": 220,
                    },
                )
            except Exception:
                missing.append(path)
                continue
            raw_content = self._raw_workspace_text(path)
            if raw_content is not None:
                result = {**result, "content": raw_content}
            memory = await self.project_memory.remember_file(
                path=str(result.get("path") or path),
                content=str(result.get("content") or ""),
            )
            snapshots[path] = (result, memory)

        direct_related: set[str] = set()
        target_snapshot = snapshots.get(target_path)
        if target_snapshot is not None:
            direct_related.update(
                self._local_import_context_paths(
                    source_path=target_path,
                    content=str(
                        target_snapshot[0].get("content") or ""
                    ),
                )
            )
        for path in sorted(direct_related):
            if path in snapshots:
                continue
            try:
                result = await self.tools.execute(
                    "workspace_read",
                    {
                        "path": path,
                        "start_line": 1,
                        "end_line": 220,
                    },
                )
            except Exception:
                continue
            raw_content = self._raw_workspace_text(path)
            if raw_content is not None:
                result = {**result, "content": raw_content}
            memory = await self.project_memory.remember_file(
                path=str(result.get("path") or path),
                content=str(result.get("content") or ""),
            )
            snapshots[path] = (result, memory)

        graph_related = set(
            await self.project_memory.related_paths(target_path)
        )
        try:
            for path, (_result, memory) in snapshots.items():
                await self.improvement.remember_orientation(
                    path=path,
                    source_sha256=memory.sha256,
                    outline=memory.outline,
                    relations=(
                        sorted(graph_related)
                        if path == target_path
                        else None
                    ),
                )
        except Exception:
            # The experience layer is optional optimization, never a task gate.
            pass
        related = sorted(
            (
                path
                for path in snapshots
                if path != target_path
            ),
            key=lambda path: (
                0 if path in direct_related else 1,
                0 if path in graph_related else 1,
                -self._focused_path_score(target_path, path),
                path.casefold(),
            ),
        )
        manifest_names = {
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "pubspec.yaml",
            "cargo.toml",
        }
        related_limit = (
            0
            if Path(target_path).name.casefold() in manifest_names
            else self.settings.supervisor_focused_related_full_files
        )
        required_related_paths = {
            *direct_related,
            *verification_context_paths,
            *evidence_context_paths,
        }
        required_related = [
            path for path in related if path in required_related_paths
        ]
        optional_related = [
            path for path in related if path not in required_related_paths
        ]
        optional_slots = max(0, related_limit - len(required_related))
        related_full = [
            *required_related,
            *optional_related[:optional_slots],
        ]
        full_paths = [
            path
            for path in [target_path, *related_full]
            if path in snapshots
        ]
        summary_paths = [
            path for path in snapshots if path not in set(full_paths)
        ]

        task_text = "\n".join(
            [
                task.title,
                *task.acceptance_criteria,
                task.verification,
            ]
        )
        creative_context = bool(
            re.search(
                r"\b(fikir|yaratıcı|yaratici|hayal|öner|oner|creative|innov)",
                task_text,
                flags=re.IGNORECASE,
            )
        )
        cards = await self.project_memory.context_cards(
            paths=list(
                dict.fromkeys([target_path, *sorted(graph_related)])
            ),
            include_hypotheses=(
                self.settings.project_memory_hypotheses_enabled
                and creative_context
            ),
        )
        cards = [
            card
            for card in cards
            if card.evidence_type != "file"
        ]
        capsule = self.attention_broker.build_capsule(
            task_text=task_text,
            target_path=target_path,
            cards=cards,
            max_chars=self.settings.project_memory_attention_budget_chars,
        )

        max_chars = self.settings.supervisor_focused_context_max_chars
        content_chars = max(1_000, max_chars - capsule.chars)
        full_budget = max(
            1_000,
            int(content_chars * 0.72) // max(1, len(full_paths)),
        )
        chunks: list[str] = [
            "PROJECT_MEMORY_V2 — görev-özel, kanıtlı ve hash tabanlı bağlam",
            capsule.text,
        ]

        if target_path not in snapshots:
            chunks.append(
                f"### HEDEF: {target_path}\nDOSYA HENÜZ YOK; oluşturulacak."
            )

        for path in full_paths:
            result, memory = snapshots[path]
            role = "HEDEF" if path == target_path else "İLGİLİ"
            raw_content = self._raw_workspace_text(path)
            content = self._focused_context_clip(
                (
                    raw_content
                    if raw_content is not None
                    else str(result.get("content") or "")
                ),
                full_budget,
            )
            chunks.append(
                f"### {role}: {path}\n"
                f"sha256={memory.sha256} state={memory.state}\n"
                f"{content}"
            )

        if summary_paths:
            outline_lines: list[str] = []
            for path in sorted(summary_paths):
                _result, memory = snapshots[path]
                outline = memory.outline.replace("\n", " | ")
                outline_lines.append(
                    f"- {path} sha256={memory.sha256[:12]} "
                    f"outline={outline}"
                )
            chunks.append(
                "### DİĞER KESİN DOSYALAR — yalnızca yerel özet\n"
                + "\n".join(outline_lines)
            )

        other_missing = [path for path in missing if path != target_path]
        if other_missing:
            chunks.append(
                "### HENÜZ OLUŞMAMIŞ DİĞER DOSYALAR\n- "
                + "\n- ".join(other_missing)
            )

        context = self._focused_context_clip(
            "\n\n".join(chunks),
            max_chars,
        )
        await self.project_memory.record_context(
            source="supervisor_focused",
            task_text=f"{task.id}:{task.title}:{target_path}",
            context_chars=len(context),
            full_file_count=len(full_paths),
            summarized_file_count=len(summary_paths),
            selected_paths=full_paths,
        )
        compiled_context = await self._compile_focused_context(
            task=task,
            task_text=task_text,
            target_path=target_path,
            snapshots=snapshots,
            full_paths=full_paths,
            summary_paths=summary_paths,
            direct_related=direct_related,
            graph_related=graph_related,
            missing=missing,
            full_budget=full_budget,
            baseline_context=context,
            include_hypotheses=creative_context,
        )
        return compiled_context or context

    async def _run_focused_agent_step(
        self,
        *,
        command_id: str,
        task_id: str,
        allowed_paths: list[str],
        instruction: str,
        phase: str,
        force_full_file: bool = False,
        transient_retry_count: int = 0,
        force_remote: bool = False,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        task = next(
            item for item in command.tasks if item.id == task_id
        )
        if len(allowed_paths) != 1:
            allowed_paths = [allowed_paths[0]]
        criteria = "\n".join(
            f"- {item}" for item in task.acceptance_criteria
        )
        context = await self._focused_context(
            task,
            target_path=allowed_paths[0],
        )
        try:
            recall = await self.improvement.recall(
                query="\n".join(
                    [
                        task.title,
                        *task.acceptance_criteria,
                        task.verification,
                    ]
                ),
                target_path=allowed_paths[0],
            )
            experience_context = recall.text
            task.task_signature = self.improvement.task_signature(
                title=task.title,
                verification=task.verification,
                paths=task.exact_files,
            )
            task.recalled_strategy_ids = recall.strategy_ids
            task.recalled_orientation_ids = recall.orientation_ids
            self._event(
                command,
                type="viewer_context_prepared",
                task_id=task.id,
                message=(
                    "Viewer proje bağlamını ve sabit bütçeli deneyim "
                    "kapsülünü hazırladı."
                ),
                data={
                    "experience_chars": recall.chars,
                    "strategy_cards": len(recall.strategy_ids),
                    "orientation_entries": len(recall.orientation_ids),
                    "lexical_only": recall.lexical_only,
                },
            )
        except Exception as exc:
            experience_context = (
                "EXPERIENCE_KERNEL_V1 — kullanılamadı; belirlenimci proje "
                "bağlamı geçerliliğini koruyor."
            )
            self._event(
                command,
                type="experience_recall_fallback",
                task_id=task.id,
                message=f"Deneyim belleği atlandı: {type(exc).__name__}",
            )

        base_content = self._raw_workspace_text(allowed_paths[0])
        patch_suffixes = {
            ".py",
            ".js",
            ".jsx",
            ".mjs",
            ".ts",
            ".tsx",
            ".html",
            ".css",
            ".json",
            ".md",
            ".sql",
            ".toml",
            ".yaml",
            ".yml",
        }
        use_safe_patch = (
            not force_full_file
            and
            base_content is not None
            and bool(base_content.strip())
            and len(base_content)
            <= self.settings.local_model_max_source_chars
            and Path(allowed_paths[0]).suffix.casefold() in patch_suffixes
        )
        base_sha256 = (
            hashlib.sha256(base_content.encode("utf-8")).hexdigest()
            if use_safe_patch and base_content is not None
            else None
        )

        retry_guidance = (
            "İlk deneme. Önceki model hatası yok."
            if not task.blocked_reason
            else (
                "Önceki deneme tamamlanamadı. Aynı çıktıyı tekrarlama; "
                "cevabı daha kısa, tam ve kesilmeden üret. Önceki hata özeti:\n"
                + task.blocked_reason[-1800:]
            )
        )

        prompt = f"""Supervisor rol-ayrımlı tek-adım yürütme sözleşmesi:

Mimari roller:
- Architect: aşağıdaki görev, dosya sözleşmesi ve kabul kriterlerini belirledi.
- Viewer: proje bağlamını ve deneyim kapsülünü salt-okunur hazırladı.
- Editor: sen yalnızca izin verilen hedef için tek güvenli değişiklik üret.
- Verifier: değişiklikten sonra ayrı ve kanıta dayalı çalışacak.

Görev:
{task.id} — {task.title}

Bu çağrının TEK amacı:
{instruction}

Bu çağrıda yazılabilecek dosyalar:
{", ".join(allowed_paths)}

Kabul kriterleri:
{criteria}

Kullanıcının bağlayıcı hedefinden ilgili bağlam:
{command.goal[:3500]}

Mevcut kesin dosyalar:
{context}

Doğrulanmış deneyim ve yönlendirme kapsülü:
{experience_context}

Uygulanmış işlem defteri:
{self._execution_ledger(task)}

Yeniden deneme yönlendirmesi:
{retry_guidance}

Kurallar:
- Yalnızca bir sonraki eksik adımı üret.
- Yalnızca izin verilen dosya yollarını kullan.
- Alternatif klasör veya dosya adı üretme.
- Bu çağrıda terminal/test çalıştırma; doğrulamayı Supervisor hazırlayacak.
- Dosya değişikliği gerekiyorsa tek bir workspace_write isteği döndür.
- Hedef dosya zaten doğruysa completed dön ve nedenini kısa yaz.
"""

        if force_remote:
            local_first = False
            local_reason = (
                "Geçici provider hatası sonrası kontrollü yeniden deneme "
                "yalnızca uzak ücretsiz rotalara yönlendirildi."
            )
        else:
            local_first, local_reason = self._local_first_decision(
                task=task,
                target_path=allowed_paths[0],
                prompt_chars=len(prompt),
                context_chars=len(context),
            )
        profile_routes = list(
            self.agents.get(task.assigned_agent).preferred_routes
        )
        if local_first:
            task.local_model_attempts += 1
            preferred_routes = [
                "local_qwen",
                "local_expert",
                *(
                    route
                    for route in profile_routes
                    if route not in {"local_qwen", "local_expert"}
                ),
            ]
            excluded_routes = None
            self._event(
                command,
                type="local_model_first_attempt_reserved",
                task_id=task.id,
                message=(
                    f"{task.id} düşük riskli ve test kapılı; yerel Qwen "
                    "ücretsiz ilk tercih olarak denenecek."
                ),
                data={
                    "route": "local_qwen",
                    "attempt": task.local_model_attempts,
                    "configured_limit": (
                        self.settings.local_model_max_attempts_per_task
                        or "unlimited"
                    ),
                    "reason": local_reason,
                },
            )
        else:
            preferred_routes = profile_routes
            excluded_routes = ["local_qwen", "local_expert"]
            self._event(
                command,
                type="local_model_skipped",
                task_id=task.id,
                message=f"Yerel ilk deneme atlandı: {local_reason}",
                data={"reason": local_reason},
            )

        task.status = "running"
        command.status = "running"
        self._set_operation(
            command,
            operation=f"task:{task.id}",
            phase=phase,
            message=(
                f"{task.id} için tek odaklı adım hazırlanıyor: "
                f"{', '.join(allowed_paths)}"
            ),
            route=(
                "local_adaptive"
                if local_first
                else "free_remote_fallback"
            ),
            reset_started_at=True,
        )
        await self.store.put(command)

        try:
            response = await self._await_with_heartbeat(
                self.agent.run(
                    AgentRequest(
                        message=prompt,
                        agent_id=task.assigned_agent,
                        routing_mode="auto",
                        max_steps=(
                            self.settings
                            .supervisor_focused_step_max_steps
                        ),
                        max_model_calls=(
                            self.settings
                            .supervisor_focused_step_max_model_calls
                        ),
                        supervised_budget=True,
                        include_trace=True,
                        allow_deterministic_tools=False,
                        additional_write_paths=allowed_paths,
                        exclusive_write_paths=allowed_paths,
                        source_evidence_pending_paths=[
                            path
                            for path in task.exact_files
                            if path != allowed_paths[0]
                        ],
                        applied_tool_fingerprints=(
                            self._applied_tool_fingerprints(task)
                        ),
                        disable_auto_context=True,
                        max_output_tokens=(
                            self.settings
                            .supervisor_focused_file_output_tokens
                        ),
                        response_protocol=(
                            "single_patch"
                            if use_safe_patch
                            else "single_file"
                        ),
                        single_file_path=allowed_paths[0],
                        single_file_base_content=(
                            base_content if use_safe_patch else None
                        ),
                        single_file_base_sha256=base_sha256,
                        preferred_routes=preferred_routes,
                        excluded_routes=excluded_routes,
                        usage_scope=command_id,
                        usage_task_id=task.id,
                        task_signature=task.task_signature,
                    )
                ),
                command_id=command_id,
                timeout_seconds=(
                    self.settings
                    .supervisor_focused_step_timeout_seconds
                ),
                heartbeat_message=(
                    f"{task.id} için tek odaklı model cevabı bekleniyor."
                ),
                heartbeat_phase=phase,
            )
        except Exception as exc:
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            budget_exhausted = self._is_mission_budget_error(exc)
            route_unavailable = self._is_route_unavailable_error(exc)
            transient_error = self._is_transient_focused_error(exc)
            timeout_message = (
                self._mission_budget_block_message(exc)
                if budget_exhausted
                else (
                    (
                        "Bu görev için şu anda uygun model rotası kalmadı. "
                        "Workspace ve üretilen dosyalar korundu; rota, bağlam "
                        "kapasitesi veya ortam değişmeden aynı çağrı "
                        f"yinelenmeyecek. Ayrıntı: {exc}"
                    )
                    if route_unavailable
                    else (
                        "Tek odaklı agent adımı tamamlanamadı: "
                        f"{type(exc).__name__}: {exc}."
                    )
                )
            )
            retry_limit = (
                self.settings.supervisor_focused_provider_retry_limit
            )
            if (
                transient_error
                and not budget_exhausted
                and not route_unavailable
                and transient_retry_count < retry_limit
            ):
                retry_number = transient_retry_count + 1
                task.failure_counts["focused_provider_transient"] = (
                    task.failure_counts.get(
                        "focused_provider_transient",
                        0,
                    )
                    + 1
                )
                task.status = "running"
                task.recovery_reason = "focused_provider_retry"
                task.blocked_reason = timeout_message
                task.last_approval_message = (
                    f"Geçici model/provider hatası algılandı. "
                    f"Kontrollü uzak rota yeniden denemesi "
                    f"{retry_number}/{retry_limit} başlatılıyor. "
                    f"Ayrıntı: {type(exc).__name__}: {exc}"
                )
                self._clear_operation(command)
                self._event(
                    command,
                    type="focused_provider_retry_scheduled",
                    task_id=task.id,
                    message=task.last_approval_message,
                    data={
                        "retry": retry_number,
                        "limit": retry_limit,
                        "force_remote": True,
                        "error_type": type(exc).__name__,
                    },
                )
                await self.store.put(command)
                return await self._run_focused_agent_step(
                    command_id=command_id,
                    task_id=task_id,
                    allowed_paths=allowed_paths,
                    instruction=instruction,
                    phase="focused_provider_retry",
                    force_full_file=force_full_file,
                    transient_retry_count=retry_number,
                    force_remote=True,
                )

            recovery_reason = (
                "mission_budget_exhausted"
                if budget_exhausted
                else (
                    "focused_route_unavailable"
                    if route_unavailable
                    else (
                        "focused_provider_timeout"
                        if transient_error
                        else "focused_step_error"
                    )
                )
            )
            if transient_error and transient_retry_count:
                timeout_message += (
                    " Kontrollü provider yeniden deneme sınırı da tükendi; "
                    "workspace ve üretilen dosyalar korundu."
                )
            elif not transient_error and not budget_exhausted:
                timeout_message += (
                    " Bu hata geçici provider hatası olarak sınıflandırılmadı; "
                    "otomatik yeniden deneme yapılmadı."
                )
            self._mark_task_blocked(
                task=task,
                recovery_reason=recovery_reason,
                message=timeout_message,
            )
            self._clear_operation(command)
            self._event(
                command,
                type=(
                    "mission_budget_exhausted"
                    if budget_exhausted
                    else (
                        "focused_provider_retry_exhausted"
                        if transient_error and transient_retry_count
                        else "focused_step_failed"
                    )
                ),
                task_id=task.id,
                message=task.last_approval_message,
                data={
                    "transient": transient_error,
                    "retry_count": transient_retry_count,
                    "retry_limit": retry_limit,
                },
            )
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

        command = await self.store.get(command_id)
        task = next(
            item for item in command.tasks if item.id == task_id
        )
        task.last_agent_response = response
        task.last_answer = response.answer
        task.last_generation_route = response.final_route
        task.last_generation_model = response.final_model

        if response.status == "awaiting_approval" and response.pending_approval is not None:
            pending_arguments = response.pending_approval.arguments
            output_path = str(pending_arguments.get("path") or allowed_paths[0])
            output_content = str(pending_arguments.get("content") or "")
            quality_issue = self._static_output_quality_issue(
                task=task,
                path=output_path,
                content=output_content,
            )
            if quality_issue is not None:
                quality_attempts = task.failure_counts.get("focused_output_quality", 0) + 1
                task.failure_counts["focused_output_quality"] = quality_attempts
                task.status = "rework_required"
                task.recovery_reason = "focused_output_quality"
                task.last_approval_message = quality_issue
                self._event(
                    command,
                    type="focused_output_quality_rejected",
                    task_id=task.id,
                    message=quality_issue,
                    data={"attempt": quality_attempts, "path": output_path},
                )
                await self.store.put(command)
                if quality_attempts <= 2:
                    return await self._run_focused_agent_step(
                        command_id=command_id,
                        task_id=task_id,
                        allowed_paths=allowed_paths,
                        instruction=(
                            instruction
                            + "\nÖnceki çıktı kalite kapısında reddedildi: "
                            + quality_issue
                            + " Bu şartı kesin olarak düzelt."
                        ),
                        phase="focused_output_quality_retry",
                    )
                self._mark_task_blocked(
                    task=task,
                    recovery_reason="focused_output_quality",
                    message=(
                        "Üretilen dosya üç kalite denemesinde de reddedildi: "
                        + quality_issue
                    ),
                )
                self._clear_operation(command)
                self._refresh_task_states(command)
                await self.store.put(command)
                return command

        if response.status == "awaiting_approval":
            self._set_pending_approval(
                command=command,
                task=task,
                response=response,
                phase="worker",
            )
            self._event(
                command,
                type="focused_file_approval_required",
                task_id=task.id,
                message=(
                    f"{task.id} için tek odaklı dosya işlemi "
                    "kullanıcı onayı bekliyor."
                ),
                data={"allowed_paths": allowed_paths},
            )
            await self.store.put(command)
            if self._auto_execution_allowed(
                command=command,
                task=task,
                tool_name=task.approval_tool or "workspace_write",
                arguments=(
                    response.pending_approval.arguments
                    if response.pending_approval is not None
                    else {}
                ),
            ):
                return await self.approve(
                    command_id=command_id,
                    task_id=task_id,
                    background=False,
                )
            return command

        if response.status == "completed":
            materialized: list[str] = []
            for path in allowed_paths:
                try:
                    await self.tools.execute(
                        "workspace_read",
                        {
                            "path": path,
                            "start_line": 1,
                            "end_line": 2,
                        },
                    )
                except Exception:
                    continue
                self._record_materialized_file(task, path)
                materialized.append(path)

            if not materialized:
                self._mark_task_blocked(
                    task=task,
                    recovery_reason="focused_completion_without_evidence",
                    message=(
                        "Agent tamamlandı dedi ancak izin verilen hedef "
                        "dosyalardan hiçbiri workspace içinde oluşmadı. "
                        "Aynı tamamlandı cevabı yeniden çalıştırılmadı."
                    ),
                )
                self._clear_operation(command)
                self._event(
                    command,
                    type="focused_completion_rejected",
                    task_id=task.id,
                    message=task.last_approval_message or "Kanıtsız tamamlanma reddedildi.",
                    data={"allowed_paths": allowed_paths},
                )
                self._refresh_task_states(command)
                await self.store.put(command)
                return command

            await self.store.put(command)
            return await self._advance_structured_task(
                command_id=command_id,
                task_id=task_id,
                reason="focused_step_completed",
            )

        protocol_failure = (
            response.status == "failed"
            and "protokol" in (response.answer or "").casefold()
        )
        if protocol_failure and use_safe_patch:
            task.last_approval_message = response.answer
            self._clear_operation(command)
            self._event(
                command,
                type="focused_patch_fell_back_to_full_file",
                task_id=task.id,
                message=(
                    "Küçük model hash-bağlı yamayı biçimleyemedi; aynı izinli "
                    "hedef için bir kez tam-dosya protokolüne düşüldü."
                ),
                data={"path": allowed_paths[0]},
            )
            await self.store.put(command)
            return await self._run_focused_agent_step(
                command_id=command_id,
                task_id=task_id,
                allowed_paths=allowed_paths,
                instruction=instruction,
                phase=phase,
                force_full_file=True,
            )
        if protocol_failure:
            self._mark_task_blocked(
                task=task,
                recovery_reason="focused_protocol_failed",
                message=(
                    response.answer
                    + " Workspace veya üretim protokolü değişmeden aynı "
                    "model çağrısı yeniden başlatılmayacak."
                ),
            )
        else:
            task.status = "rework_required"
            task.recovery_reason = f"focused_step_{response.status}"
            task.last_approval_message = response.answer
        self._clear_operation(command)
        self._event(
            command,
            type="focused_step_incomplete",
            task_id=task.id,
            message=task.last_approval_message or response.answer,
            data={
                "status": response.status,
                "protocol_failure": protocol_failure,
            },
        )
        self._refresh_task_states(command)
        await self.store.put(command)
        return command

    def _local_first_decision(
        self,
        *,
        task: SupervisorTask,
        target_path: str,
        prompt_chars: int,
        context_chars: int,
    ) -> tuple[bool, str]:
        if not self.settings.local_model_enabled:
            return False, "Yerel model yapılandırmada kapalı."
        configured_limit = self.settings.local_model_max_attempts_per_task
        if (
            configured_limit > 0
            and
            task.local_model_attempts
            >= configured_limit
        ):
            return (
                False,
                f"Bu görev yapılandırılmış {configured_limit} yerel deneme "
                "sınırına ulaştı.",
            )
        if self._verification_arguments(task) is None:
            return False, "Görevin güvenli ve çalıştırılabilir test kapısı yok."
        if prompt_chars > self.settings.local_model_max_input_chars:
            return (
                False,
                "Derlenmiş istek güvenli yerel bağlam sınırını aşıyor.",
            )
        if context_chars > self.settings.local_model_max_source_chars:
            return (
                False,
                "Kaynak kanıtı yerel küçük-model sınırından büyük.",
            )

        suffix = Path(target_path).suffix.casefold()
        supported = {
            ".css",
            ".html",
            ".js",
            ".json",
            ".jsx",
            ".md",
            ".mjs",
            ".py",
            ".sql",
            ".ts",
            ".tsx",
        }
        if suffix not in supported:
            return False, f"`{suffix or 'uzantısız'}` yerel rota için uygun değil."

        risk_text = " ".join(
            [
                target_path,
                task.title,
                *task.acceptance_criteria,
            ]
        ).casefold()
        high_risk = re.compile(
            r"\b("
            r"auth|authentication|authorization|security|crypto|cryptography|"
            r"password|secret|token|payment|billing|migration|production|"
            r"deployment|permission|credential|kimlik|yetki|güvenlik|şifre|"
            r"ödeme|faturalama|geçiş|canlıya"
            r")\b",
            flags=re.IGNORECASE,
        )
        if high_risk.search(risk_text):
            return False, "Görev güvenlik veya operasyon açısından yüksek riskli."

        return True, "Tek dosya, kısa bağlam ve deterministik test kapısı."

    @staticmethod
    def _static_output_quality_issue(
        *,
        task: SupervisorTask,
        path: str,
        content: str,
    ) -> str | None:
        if Path(path).suffix.casefold() != ".html":
            return None
        title = task.title.casefold()
        contract_text = " ".join(
            [task.title, *task.acceptance_criteria]
        ).casefold()
        classic_module_scripts = re.findall(
            r"<script\b(?![^>]*\btype\s*=\s*['\"]module['\"])[^>]*\bsrc\s*=\s*"
            r"['\"][^'\"]*\.module\.js(?:\?[^'\"]*)?['\"][^>]*>",
            content,
            flags=re.IGNORECASE,
        )
        if classic_module_scripts:
            return (
                "ES module dosyası klasik script olarak yüklenemez. "
                "three.module.js için type=\"module\" ve import kullan veya "
                "global THREE sağlayan three.min.js sürümünü yükle."
            )
        if "calculator" in contract_text or "hesap makinesi" in contract_text:
            if re.search(r"\beval\s*\(", content, flags=re.IGNORECASE):
                return "Hesap makinesi çıktısı eval() kullanamaz."
            if re.search(r"\b(?:new\s+)?Function\s*\(", content):
                return "Hesap makinesi çıktısı Function constructor kullanamaz."
            if re.search(
                r"!\s*(?:current|expression|input)\.includes\(\s*['\"]\.['\"]\s*\)",
                content,
                flags=re.IGNORECASE,
            ):
                return (
                    "Ondalık ayırıcı kontrolü tüm ifadeyi değil yalnızca mevcut "
                    "sayı parçasını denetlemeli."
                )
            required_labels = ("C", "DEL", "+", "-", "*", "/", ".", "=")
            missing = [label for label in required_labels if label not in content]
            if missing:
                return "Hesap makinesi zorunlu kontrolleri eksik: " + ", ".join(missing)

        planet_intent = re.search(
            r"\b(?:3d|3b|gezegen|planet|dunya|dünya|webgl|three\.js)\b",
            contract_text,
        )
        if planet_intent:
            planet_issues: list[str] = []
            function_names = re.findall(
                r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", content
            )
            duplicate_functions = sorted(
                {name for name in function_names if function_names.count(name) > 1}
            )
            if duplicate_functions:
                planet_issues.append(
                    "Aynı JavaScript fonksiyonu birden fazla kez tanımlanmış: "
                    + ", ".join(duplicate_functions)
                    + "."
                )
            invalid_three_calls = []
            if re.search(r"\bscene\.lighting\s*\(", content):
                invalid_three_calls.append("scene.lighting()")
            if re.search(r"(?<![.\w])position\s*\(\s*camera\b", content):
                invalid_three_calls.append("position(camera, ...)")
            if re.search(r"\bnew\s+(?:AmbientLight|PointLight|SpotLight)\b", content):
                invalid_three_calls.append("THREE. öneki olmayan ışık sınıfı")
            if invalid_three_calls:
                planet_issues.append(
                    "Geçersiz Three.js kullanımı bulundu: "
                    + ", ".join(invalid_three_calls)
                    + "."
                )
            if "requestAnimationFrame" not in content:
                planet_issues.append(
                    "3B gezegen çıktısında sürekli render döngüsü bulunmuyor."
                )
            if not re.search(r"\.rotation\.[xyz]\s*(?:\+=|-=|=)", content):
                planet_issues.append(
                    "Gezegenin dönüş açısını değiştiren bir işlem bulunmuyor."
                )
            if not re.search(
                r"\brenderer\.render\s*\(\s*scene\s*,\s*camera\s*\)",
                content,
            ):
                planet_issues.append(
                    "Animasyon döngüsü sahneyi renderer.render(scene, camera) ile çizmiyor."
                )
            if not re.search(r"TextureLoader|CanvasTexture|\bmap\s*:", content):
                planet_issues.append(
                    "Gezegen yüzeyinde dönüşü görünür kılacak doku veya "
                    "ayırt edilebilir yüzey detayı bulunmuyor. Çıktıda "
                    "THREE.CanvasTexture veya THREE.TextureLoader kullan."
                )
            if not re.search(
                r"pointer(?:down|move)|mouse(?:down|move)|rotate-(?:left|right)|"
                r"sola\s+döndür|sağa\s+döndür",
                content,
                flags=re.IGNORECASE,
            ):
                planet_issues.append(
                    "Kullanıcının gezegeni döndürebileceği gerçek bir kontrol "
                    "bulunmuyor. Sürükleme için pointerdown ve pointermove "
                    "olaylarını birlikte uygula; görünür yön düğmeleri de ekle."
                )
            if planet_issues:
                return " ".join(planet_issues)
        return None

    async def _run_verification_repair(
        self,
        *,
        command_id: str,
        task_id: str,
        result: dict[str, Any],
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        task = next(
            item for item in command.tasks if item.id == task_id
        )
        if result.get("duplicate_blocked") is True:
            original = result.get("original_result")
            if isinstance(original, dict):
                result = original

        task.verification_failures += 1
        diagnosis, count, repair_state_changed = (
            self._record_verification_failure(
                command=command,
                task=task,
                result=result,
            )
        )
        await self._record_improvement_outcome(
            command=command,
            task=task,
            success=False,
            failure_kind=diagnosis.kind,
        )

        same_failure_limit = self.settings.supervisor_same_failure_limit
        should_block_repair = self._should_block_repeated_failure(
            count=count,
            limit=same_failure_limit,
            repair_state_changed=repair_state_changed,
        )
        if should_block_repair:
            blocked_message = (
                f"Aynı {diagnosis.kind} hatası {count} kez tekrarlandı. "
                "Prometheus aynı komutu veya aynı dosya varyasyonunu yeniden "
                "onaya sunmayı durdurdu."
            )
            self._mark_task_blocked(
                task=task,
                recovery_reason="repeated_failure_blocked",
                message=blocked_message,
            )
            self._clear_operation(command)
            self._event(
                command,
                type="repair_loop_blocked",
                task_id=task.id,
                message=task.blocked_reason,
                data={
                    "signature": diagnosis.signature,
                    "kind": diagnosis.kind,
                    "count": count,
                    "repair_state_changed": repair_state_changed,
                },
            )
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

        if (
            diagnosis.retry_tool
            and diagnosis.retry_arguments
            and diagnosis.strategy_key
            and diagnosis.strategy_key not in task.attempted_strategies
        ):
            task.attempted_strategies.append(diagnosis.strategy_key)
            approval_created, auto_result = (
                await self._set_supervisor_pending_approval(
                    command=command,
                    task=task,
                    tool_name=diagnosis.retry_tool,
                    arguments=diagnosis.retry_arguments,
                    reason=(
                        f"Prometheus hata sınıflandırıcısı yeni strateji seçti: "
                        f"{diagnosis.summary}"
                    ),
                )
            )
            self._event(
                command,
                type="deterministic_repair_strategy_selected",
                task_id=task.id,
                message=(
                    f"{diagnosis.strategy_key} stratejisi seçildi; "
                    "kaynak dosyalar rastgele değiştirilmedi."
                ),
                data={"signature": diagnosis.signature},
            )
            await self.store.put(command)
            if not approval_created and auto_result is not None:
                return await self._advance_structured_task(
                    command_id=command_id,
                    task_id=task_id,
                    reason="deterministic_repair_auto_applied",
                    last_tool_name=diagnosis.retry_tool,
                    last_result=auto_result,
                )
            return command

        if diagnosis.kind in {
            "toolchain_installer_unavailable",
            "node_toolchain_install_failed",
            "npm_install_failed",
            "missing_command",
        }:
            blocked_message = (
                f"{diagnosis.summary} Aynı doğrulama yeniden "
                "çalıştırılmayacak. Ortamda gerçek bir değişiklik olmadan "
                "Devam Et düğmesi görevi tekrar başlatmayacak."
            )
            self._mark_task_blocked(
                task=task,
                recovery_reason="external_prerequisite_blocked",
                message=blocked_message,
            )
            self._clear_operation(command)
            self._event(
                command,
                type="external_prerequisite_blocked",
                task_id=task.id,
                message=task.blocked_reason,
                data={
                    "signature": diagnosis.signature,
                    "kind": diagnosis.kind,
                    "strategy_attempted": diagnosis.strategy_key,
                },
            )
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

        deterministic_repair = await self._try_deterministic_contract_repair(
            command=command,
            task=task,
            result=result,
            failure_kind=diagnosis.kind,
        )
        if deterministic_repair is not None:
            return deterministic_repair

        output = (
            f"Hata sınıfı: {diagnosis.kind}\n"
            f"Özet: {diagnosis.summary}\n"
            f"Exit code: {result.get('exit_code')}\n"
            f"STDOUT:\n{result.get('stdout', '')}\n"
            f"STDERR:\n{result.get('stderr', '')}"
        )
        self_fix = TDDSelfFixLoop(
            command_id=command.id,
            max_retries=self.settings.supervisor_max_task_attempts,
            current_attempt=max(0, task.verification_failures - 1),
        )
        try:
            replan_strategy = self_fix.record_failure_and_generate_replan(
                error_message=diagnosis.summary,
                traceback_snippet=output[:8_000],
                timestamp=utc_now(),
            )
        except TDDSelfFixMaxRetriesExceeded:
            blocked_message = (
                "TDD self-fix toplam deneme sınırına ulaştı. Yeni kanıt veya "
                "workspace değişikliği olmadan başka model çağrısı yapılmayacak."
            )
            self._mark_task_blocked(
                task=task,
                recovery_reason="tdd_self_fix_exhausted",
                message=blocked_message,
            )
            self._clear_operation(command)
            self._event(
                command,
                type="tdd_self_fix_exhausted",
                task_id=task.id,
                message=blocked_message,
                data={"verification_failures": task.verification_failures},
            )
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

        self._event(
            command,
            type="tdd_self_fix_replan_generated",
            task_id=task.id,
            message=(
                f"Kanıta dayalı TDD onarım planı "
                f"{task.verification_failures}/"
                f"{self.settings.supervisor_max_task_attempts} üretildi."
            ),
            data={
                "failure_kind": diagnosis.kind,
                "attempt": task.verification_failures,
            },
        )
        repair_path = self._verification_repair_path(
            task=task,
            result=result,
            failure_kind=diagnosis.kind,
        )
        self._event(
            command,
            type="verification_repair_target_selected",
            task_id=task.id,
            message=(
                f"Doğrulama kanıtına göre onarım hedefi "
                f"`{repair_path}` seçildi."
            ),
            data={
                "failure_kind": diagnosis.kind,
                "repair_path": repair_path,
            },
        )
        await self.store.put(command)
        return await self._run_focused_agent_step(
            command_id=command_id,
            task_id=task_id,
            allowed_paths=[repair_path],
            instruction=(
                replan_strategy
                + "\n\nBu doğrulama hatası için yalnızca gerçekten gerekli "
                "tek dosya değişikliğini hazırla. Aynı içerik veya yalnızca "
                "biçim/boşluk varyasyonu üretme.\n\n"
                + output[:10000]
            ),
            phase="focused_verification_repair",
        )

    async def _try_deterministic_contract_repair(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        result: dict[str, Any],
        failure_kind: str,
    ) -> SupervisorCommand | None:
        if failure_kind != "assertion_failure":
            return None

        writable_python = [
            path
            for path in task.exact_files
            if path.casefold().endswith(".py")
            and not re.search(
                r"(?:^|/)(?:tests?|__tests__)/",
                path.replace("\\", "/").casefold(),
            )
        ]
        if len(writable_python) != 1:
            return None
        target_path = writable_python[0]
        target_source = self._raw_workspace_text(target_path)
        if target_source is None:
            return None

        contract_sources: list[str] = []
        for path in self._verification_context_paths(task):
            if path == target_path or not path.casefold().endswith(".py"):
                continue
            source = self._raw_workspace_text(path)
            if source is not None:
                contract_sources.append(source)
        if not contract_sources:
            return None

        failure_output = "\n".join(
            str(result.get(key) or "")
            for key in ("stdout", "stderr", "error", "reason")
        )
        repair = build_fastapi_status_code_repair(
            target_path=target_path,
            target_source=target_source,
            contract_sources=contract_sources,
            failure_output=failure_output,
        )
        if repair is None or repair.strategy_key in task.attempted_strategies:
            return None

        task.attempted_strategies.append(repair.strategy_key)
        approval_created, auto_result = (
            await self._set_supervisor_pending_approval(
                command=command,
                task=task,
                tool_name="workspace_write",
                arguments={
                    "path": repair.path,
                    "content": repair.content,
                },
                reason=(
                    "Pytest sözleşmesi ile FastAPI route decoratorü arasında "
                    "tek anlamlı HTTP status farkı bulundu: "
                    + "; ".join(repair.changes)
                ),
            )
        )
        self._event(
            command,
            type="deterministic_contract_repair_selected",
            task_id=task.id,
            message=(
                "Model çağrısı yapılmadan, salt-okunur pytest sözleşmesine "
                "dayalı FastAPI status_code düzeltmesi hazırlandı."
            ),
            data={
                "path": repair.path,
                "changes": list(repair.changes),
                "strategy_key": repair.strategy_key,
            },
        )
        await self.store.put(command)
        if not approval_created and auto_result is not None:
            return await self._advance_structured_task(
                command_id=command.id,
                task_id=task.id,
                reason="deterministic_contract_repair_auto_applied",
                last_tool_name="workspace_write",
                last_result=auto_result,
            )
        return command

    @staticmethod
    def _verification_repair_path(
        *,
        task: SupervisorTask,
        result: dict[str, Any],
        failure_kind: str,
    ) -> str:
        if not task.exact_files:
            raise ValueError(
                "Doğrulama onarımı için kesin dosya bulunamadı."
            )

        output = "\n".join(
            str(result.get(key) or "")
            for key in ("stdout", "stderr", "error", "reason")
        )
        normalized_output = output.replace("\\", "/").casefold()
        scored: list[tuple[int, int, str]] = []
        for index, path in enumerate(task.exact_files):
            normalized_path = path.replace("\\", "/").removeprefix("./")
            folded_path = normalized_path.casefold()
            basename = Path(normalized_path).name.casefold()
            full_mentions = normalized_output.count(folded_path)
            basename_mentions = normalized_output.count(basename)
            score = full_mentions * 100 + basename_mentions * 10
            is_test_path = bool(
                re.search(
                    r"(?:^|/)(?:tests?|__tests__)/|"
                    r"\.(?:test|spec)\.[^.]+$",
                    folded_path,
                )
            )
            if (
                failure_kind in {"assertion_failure", "test_discovery"}
                and is_test_path
            ):
                score += 20
            if (
                failure_kind
                in {
                    "missing_package_manifest",
                    "invalid_package_manifest",
                    "missing_npm_script",
                }
                and basename == "package.json"
            ):
                score += 200
            scored.append((score, -index, path))

        best_score, _order, best_path = max(scored)
        if best_score > 0:
            return best_path

        if failure_kind in {"assertion_failure", "test_discovery"}:
            test_path = next(
                (
                    path
                    for path in task.exact_files
                    if re.search(
                        r"(?:^|/)(?:tests?|__tests__)/|"
                        r"\.(?:test|spec)\.[^.]+$",
                        path.replace("\\", "/").casefold(),
                    )
                ),
                None,
            )
            if test_path is not None:
                return test_path

        return task.exact_files[0]

    async def _verification_preflight(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        arguments: dict[str, Any],
    ) -> tuple[bool, SupervisorCommand | None]:
        terminal = self.tools.get("safe_terminal")
        preflight = getattr(terminal, "preflight", None)
        if preflight is None:
            return True, None

        result = await preflight(arguments)
        if result.get("ready") is True:
            return True, None

        remediation = result.get("remediation")
        if isinstance(remediation, dict):
            tool_name = str(remediation.get("tool") or "")
            tool_arguments = remediation.get("arguments")
            if tool_name and isinstance(tool_arguments, dict):
                approval_created, auto_result = (
                    await self._set_supervisor_pending_approval(
                        command=command,
                        task=task,
                        tool_name=tool_name,
                        arguments=tool_arguments,
                        reason=(
                            "Doğrulama ön kontrolü gerekli ortam adımını "
                            f"belirledi: {result.get('message') or result.get('failure_kind')}."
                        ),
                    )
                )
                self._event(
                    command,
                    type="verification_preflight_remediation",
                    task_id=task.id,
                    message=(
                        "Başarısız olacağı bilinen test çalıştırılmadı; "
                        "önce gerekli araç/bağımlılık adımı hazırlandı."
                    ),
                    data={
                        "failure_kind": result.get("failure_kind"),
                        "remediation_tool": tool_name,
                        "approval_created": approval_created,
                    },
                )
                await self.store.put(command)
                if not approval_created and auto_result is not None:
                    advanced = await self._advance_structured_task(
                        command_id=command.id,
                        task_id=task.id,
                        reason="preflight_remediation_auto_applied",
                        last_tool_name=tool_name,
                        last_result=auto_result,
                    )
                    return False, advanced
                return False, command

        suggested = result.get("suggested_files") or []
        message = str(result.get("message") or result.get("failure_kind") or "Doğrulama ön koşulu eksik.")
        allowed = list(dict.fromkeys([*task.exact_files, *[str(item) for item in suggested]]))
        if suggested and all(str(item) in task.exact_files for item in suggested):
            advanced = await self._run_focused_agent_step(
                command_id=command.id,
                task_id=task.id,
                allowed_paths=allowed,
                instruction=(
                    "Doğrulama ön kontrolü şu manifest/yapılandırma "
                    f"sorununu buldu: {message}. Yalnızca gerekli dosyayı düzelt."
                ),
                phase="verification_preflight_repair",
            )
            return False, advanced

        self._mark_task_blocked(
            task=task,
            recovery_reason="planning_contract_incomplete",
            message=(
                f"{message} Plan bu düzeltme için izinli kesin dosyaları "
                "içermiyor; belirsiz worker döngüsü başlatılmadı."
            ),
        )
        self._clear_operation(command)
        self._event(
            command,
            type="planning_contract_blocked",
            task_id=task.id,
            message=task.blocked_reason or message,
            data={"suggested_files": suggested},
        )
        self._refresh_task_states(command)
        await self.store.put(command)
        return False, command

    async def _advance_structured_task(
        self,
        *,
        command_id: str,
        task_id: str,
        reason: str,
        last_tool_name: str | None = None,
        last_result: Any | None = None,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        task = next(
            item for item in command.tasks if item.id == task_id
        )

        focused_protocol_changed = (
            self._reconcile_focused_generation_revision(
                command=command,
                task=task,
            )
        )
        runtime_changed = self._reconcile_terminal_runtime_revision(
            command=command,
            task=task,
        )
        environment_changed = self._reconcile_environment_revision(
            command=command,
            task=task,
        )
        if focused_protocol_changed or runtime_changed or environment_changed:
            task.status = "running"
            command.status = "running"
            await self.store.put(command)

        await self._synchronize_workspace_evidence(task)
        verification = self._latest_successful_verification(task)
        if verification is not None and task.workspace_state_validated:
            task.effective_verification = self._command_text(
                verification.result
            )
            task.successful_verification_version = verification.version
            if task.attempted_strategies:
                task.verification_strategy = task.attempted_strategies[-1]
            else:
                task.verification_strategy = "declared_verification"
            completion = await self._local_completion_response(
                task=task,
                tool_name="safe_terminal",
                result=verification.result,
            )
            if completion is not None:
                task.recovery_reason = None
                await self._handle_worker_response(
                    command=command,
                    task=task,
                    response=completion,
                )
                self._clear_operation(command)
                self._refresh_task_states(command)
                await self.store.put(command)
                return command

        if (
            last_tool_name == "safe_terminal"
            and isinstance(last_result, dict)
            and last_result.get("success") is False
        ):
            return await self._run_verification_repair(
                command_id=command_id,
                task_id=task_id,
                result=last_result,
            )

        existing_verification_marker = "verification_first_existing_targets"
        existing_exact_targets = bool(task.exact_files) and all(
            self._workspace_file_is_materialized(path)
            for path in task.exact_files
        )
        if (
            existing_exact_targets
            and not self._has_applied_workspace_write(task)
            and existing_verification_marker not in task.attempted_strategies
        ):
            task.attempted_strategies.append(existing_verification_marker)
            self._event(
                command,
                type="existing_target_verification_first",
                task_id=task.id,
                message=(
                    "Kesin hedef dosyalar workspace içinde zaten mevcut. "
                    "Model çağrısından önce görev doğrulaması çalıştırılacak."
                ),
                data={"paths": list(task.exact_files)},
            )
            await self.store.put(command)

        target = self._next_unmaterialized_file(task)
        if target is not None:
            return await self._run_focused_agent_step(
                command_id=command_id,
                task_id=task_id,
                allowed_paths=[target],
                instruction=(
                    f"`{target}` kesin hedef dosyasını görev "
                    "kriterlerine uygun biçimde oluştur veya düzelt."
                ),
                phase="focused_file_generation",
            )

        verification_arguments = self._verification_arguments(task)
        if verification_arguments is None:
            task.status = "rework_required"
            task.recovery_reason = "unsupported_verification"
            task.last_approval_message = (
                "Doğrulama komutu güvenli terminal presetine "
                f"dönüştürülemedi: {task.verification}"
            )
            self._clear_operation(command)
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

        preflight_ready, preflight_command = (
            await self._verification_preflight(
                command=command,
                task=task,
                arguments=verification_arguments,
            )
        )
        if not preflight_ready:
            assert preflight_command is not None
            return preflight_command

        approval_created, auto_result = (
            await self._set_supervisor_pending_approval(
                command=command,
                task=task,
                tool_name="safe_terminal",
                arguments=verification_arguments,
                reason=(
                    f"Kesin dosyalar hazır. Güvenli işlem "
                    f"{task.approval_version + 1}: "
                    f"`{task.verification}` doğrulamasını çalıştır."
                ),
            )
        )
        await self.store.put(command)
        if not approval_created and auto_result is not None:
            return await self._advance_structured_task(
                command_id=command_id,
                task_id=task_id,
                reason="scoped_verification_auto_applied",
                last_tool_name="safe_terminal",
                last_result=auto_result,
            )
        return command

    async def _local_completion_response(
        self,
        *,
        task: SupervisorTask,
        tool_name: str,
        result: Any,
    ) -> AgentResponse | None:
        if tool_name != "safe_terminal":
            return None
        if not self._verification_command_matches(task, result):
            return None
        if not await self._exact_files_exist(task):
            return None

        await self._synchronize_workspace_evidence(task)
        if task.exact_files and not task.workspace_state_validated:
            return None

        trace: list[AgentStep] = []
        for path in task.exact_files:
            try:
                read_result = await self.tools.execute(
                    "workspace_read",
                    {"path": path, "start_line": 1, "end_line": 5},
                )
            except Exception:
                return None
            trace.append(
                AgentStep(
                    step=len(trace) + 1,
                    selected_route="deterministic",
                    provider="local-tool",
                    model="workspace-evidence",
                    action="tool",
                    reason="Kesin hedef dosya workspace içinde doğrulandı.",
                    tool="workspace_read",
                    arguments={"path": path},
                    tool_result=read_result,
                    latency_ms=0,
                    raw_output=None,
                )
            )
        for record in task.approval_history:
            if record.state != "applied" or not record.tool:
                continue
            trace.append(
                AgentStep(
                    step=len(trace) + 1,
                    selected_route="deterministic",
                    provider="local-tool",
                    model="execution-ledger",
                    action="tool",
                    reason=record.description,
                    tool=record.tool,
                    arguments=record.preview or {},
                    tool_result=(
                        record.result
                        if record.result is not None
                        else {"state": record.state}
                    ),
                    latency_ms=0,
                    raw_output=None,
                )
            )

        result_text = json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )
        return AgentResponse(
            answer=(
                "Uygulama ve doğrulama araç kanıtları tamamlandı.\n"
                f"Değiştirilen hedefler: {', '.join(task.exact_files)}\n"
                f"Tanımlı doğrulama: {task.verification}\n"
                f"Gerçek başarılı doğrulama: "
                f"{self._command_text(result)}\n"
                f"Araç sonucu: {result_text}\n"
                "Doğrulama Durumu: Başarılı araç kanıtı yerel teslim "
                "kapısı tarafından doğrulandı."
            ),
            agent_id=task.assigned_agent,
            agent_name=f"{task.assigned_agent} evidence gate",
            status="completed",
            steps_used=len(trace),
            model_calls_used=0,
            tools_used=list(
                dict.fromkeys(
                    step.tool for step in trace if step.tool
                )
            ),
            final_route="deterministic_evidence_gate",
            final_provider="local",
            final_model="execution-evidence-gate",
            trace=trace,
        )

    def _assignment_prompt(
        self,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> str:
        evidence_items = [
            item
            for item in task.evidence
            if item.get("type") != "user_request"
        ]
        evidence = "\n".join(
            f"- {item['type']}: {item['value']}"
            for item in evidence_items
        ) or "- Doğrulanmış ek dosya kanıtı yok."
        criteria = "\n".join(
            f"- {item}"
            for item in task.acceptance_criteria
        )
        dependencies = ", ".join(task.dependencies) or "yok"
        exact_files = ", ".join(task.exact_files) or "yok"

        return f"""Supervisor tarafından atanan sınırlı görev:

Görev:
{task.id} — {task.title}

Öncelik: {task.priority}
Doğrulanmış proje kanıtı:
{evidence}

Kabul kriterleri:
{criteria}

Bağımlılıklar: {dependencies}
Doğrulama yöntemi: {task.verification}
Kesin ve izinli hedef dosyalar: {exact_files}

Önceki işlem özeti:
{task.last_approval_message or "Yok"}

Kanıt uzlaştırma durumu:
- Eksik kesin dosyalar: {", ".join(task.reconciliation_missing_files) or "henüz kontrol edilmedi"}
- Başarılı doğrulama kanıtı: {"var" if task.reconciliation_verification_found else "yok/henüz kontrol edilmedi"}

UYGULANMIŞ İŞLEM DEFTERİ — bunları tekrar çalıştırma:
{self._execution_ledger(task)}

Bağlayıcı kurallar:
- Yalnızca bu görevi tamamla; diğer görev veya dosyalara geçme.
- Kesin dosya yolları MUTLAK GÖREV SÖZLEŞMESİDİR.
- `score.py` istendiyse `backend/score.py`, `app/score.py` veya başka alternatif üretme.
- Kesin dosya yollarını değiştirme veya alternatif klasör üretme.
- Kesin dosyalar dışındaki mevcut üretim bileşenlerini değiştirme.
- APPLIED işlemleri ve başarılı doğrulamaları tekrar etme.
- changed=false olacak aynı içerikli yazma hazırlama.
- Önce eksik kesin dosyaları oku/oluştur, sonra doğrulamayı bir kez çalıştır.
- Görevde yazan doğrulama yöntemini teknoloji sözleşmesi kabul et; agent rolünden
  farklı bir test aracı varsayma.
- Kabul kriterleri kanıtlandıysa yeni araç istemeden final teslim üret.
- Final cevapta yalnızca değişen dosyalar ve doğrulama kanıtını özetle."""

    @staticmethod
    def _task_evidence(response: AgentResponse) -> list[str]:
        evidence: list[str] = []
        if response.trace:
            for step in response.trace:
                if not step.tool or not isinstance(step.tool_result, dict):
                    continue
                if step.tool == "workspace_write":
                    path = step.tool_result.get("path")
                    changed = step.tool_result.get("changed")
                    if path:
                        evidence.append(
                            f"workspace_write:{path}:changed={changed}"
                        )
                elif step.tool == "safe_terminal":
                    evidence.append(
                        "safe_terminal:"
                        f"exit_code={step.tool_result.get('exit_code')}:"
                        f"success={step.tool_result.get('success')}"
                    )
                elif step.tool in {
                    "workspace_read",
                    "workspace_search",
                    "git_diff",
                    "git_status",
                }:
                    evidence.append(step.tool)
        return list(dict.fromkeys(evidence))

    async def _record_improvement_outcome(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        success: bool,
        failure_kind: str | None = None,
    ) -> None:
        """Persist evidence-gated outcomes without ever blocking delivery."""

        try:
            await self.improvement.record_verified_outcome(
                command_id=command.id,
                task_id=task.id,
                goal=command.goal,
                title=task.title,
                verification=(
                    task.effective_verification or task.verification
                ),
                files=task.exact_files,
                evidence=(
                    self._task_evidence(task.last_agent_response)
                    if task.last_agent_response is not None
                    else []
                ),
                success=success,
                failure_kind=failure_kind,
                route_key=task.last_generation_route,
                model=task.last_generation_model,
                recalled_strategy_ids=task.recalled_strategy_ids,
                recalled_orientation_ids=task.recalled_orientation_ids,
            )
            if task.task_signature and task.last_generation_route:
                await self.agent.orchestrator.store.record_verified_task_route(
                    task_signature=task.task_signature,
                    route_key=task.last_generation_route,
                    success=success,
                )
        except Exception as exc:
            self._event(
                command,
                type="experience_record_fallback",
                task_id=task.id,
                message=(
                    "Görev sonucu geçerli; deneyim kaydı ayrı bir "
                    f"optimizasyon hatasıyla atlandı: {type(exc).__name__}"
                ),
            )

    async def _review(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> None:
        # Objective delivery tasks that already passed the local execution
        # evidence gate are independently reviewed without another provider
        # call. This reviewer only trusts exact files and successful terminal
        # evidence, never the producer's prose.
        if (
            task.last_agent_response is not None
            and task.last_agent_response.final_route
            == "deterministic_evidence_gate"
            and task.exact_files
            and await self._exact_files_exist(task)
        ):
            successful_verification = next(
                (
                    record
                    for record in reversed(task.approval_history)
                    if record.tool == "safe_terminal"
                    and record.state == "applied"
                    and record.success is True
                    and self._verification_command_matches(
                        task,
                        record.result,
                    )
                ),
                None,
            )
            if successful_verification is not None:
                task.status = "completed"
                effective = (
                    task.effective_verification
                    or self._command_text(successful_verification.result)
                )
                await self.project_memory.record_evidence(
                    claim=(
                        f"{task.id} verification passed for "
                        f"{', '.join(task.exact_files)}."
                    ),
                    evidence_type="test",
                    evidence_ref=effective,
                    confidence=1.0,
                )
                task.review_answer = (
                    "KABUL — Independent Evidence Reviewer: kesin dosyalar "
                    "workspace içinde doğrulandı ve terminal doğrulaması "
                    f"exit code 0 ile tamamlandı: {effective}"
                )
                self._clear_approval_payload(
                    task,
                    state="applied",
                    message="Independent Evidence Reviewer görevi kabul etti.",
                )
                command.handoffs.append(
                    SupervisorHandoff(
                        id=secrets.token_urlsafe(8),
                        task_id=task.id,
                        type="review_accept",
                        from_agent="evidence_reviewer",
                        to_agent="supervisor",
                        summary=task.review_answer,
                        evidence=self._task_evidence(
                            task.last_agent_response
                        ),
                    )
                )
                self._event(
                    command,
                    type="task_evidence_review_accepted",
                    task_id=task.id,
                    message=(
                        f"{task.id}, Independent Evidence Reviewer "
                        "tarafından kabul edildi."
                    ),
                )
                self._refresh_task_states(command)
                await self.store.put(command)
                if command.auto_run and command.status not in {
                    "completed",
                    "failed",
                    "awaiting_approval",
                    "waiting_decision",
                }:
                    self._spawn(
                        self.advance(command_id=command.id, background=True),
                        command_id=command.id,
                        operation="auto_advance",
                    )
                return

        task.status = "reviewing"
        command.status = "reviewing"
        self._set_operation(
            command,
            operation=f"review:{task.id}",
            phase="independent_review",
            message=f"Reviewer {task.id} kanıtlarını inceliyor.",
            route="auto",
            reset_started_at=True,
        )
        await self.store.put(command)
        self._event(
            command,
            type="review_started",
            task_id=task.id,
            message=f"{task.id} bağımsız incelemeye gönderildi.",
        )
        handoff = SupervisorHandoff(
            id=secrets.token_urlsafe(8),
            task_id=task.id,
            type="review_request",
            from_agent=task.assigned_agent,
            to_agent="reviewer",
            summary=task.last_answer or "",
            evidence=self._task_evidence(
                task.last_agent_response
                or AgentResponse(
                    answer="",
                    agent_id=task.assigned_agent,
                    agent_name=task.assigned_agent,
                    status="failed",
                    steps_used=0,
                    model_calls_used=0,
                    tools_used=[],
                )
            ),
        )
        command.handoffs.append(handoff)

        review_prompt = f"""Bağımsız Reviewer görevi:

Komut hedefi:
{command.goal}

İncelenen görev:
{task.id} — {task.title}

Kabul kriterleri:
{json.dumps(task.acceptance_criteria, ensure_ascii=False)}

Üretici agent:
{task.assigned_agent}

Üretici final cevabı:
{task.last_answer}

Araç kanıtları:
{json.dumps(handoff.evidence, ensure_ascii=False)}

Uygulama işlem defteri:
{self._execution_ledger(task)}

Başarılı ve görev doğrulamasıyla eşleşen terminal kanıtını gereksiz yere yeniden çalıştırma.
Gerçek workspace, diff ve test kanıtlarını incele.
Cevabın ilk kelimesi mutlaka KABUL veya RET olsun.
KABUL yalnızca kabul kriterleri yeterli kanıtla karşılanıyorsa ver.
RET verirsen somut yeniden çalışma görevini yaz."""

        try:
            review = await self._await_with_heartbeat(
                self.agent.run(
                    AgentRequest(
                        message=review_prompt,
                        agent_id="reviewer",
                        routing_mode="auto",
                        max_steps=12,
                        max_model_calls=14,
                        supervised_budget=True,
                        include_trace=True,
                        allow_deterministic_tools=False,
                        usage_scope=command.id,
                        usage_task_id=task.id,
                    )
                ),
                command_id=command.id,
                timeout_seconds=(
                    self.settings.supervisor_reviewer_timeout_seconds
                ),
                heartbeat_message=(
                    f"Reviewer {task.id} kanıtlarını inceliyor."
                ),
                heartbeat_phase="independent_review",
            )
        except TimeoutError as exc:
            task.status = "rework_required"
            task.recovery_reason = "reviewer_timeout"
            task.review_answer = str(exc)
            self._clear_operation_if(command, f"review:{task.id}")
            self._event(
                command,
                type="review_timeout_recovered",
                task_id=task.id,
                message=(
                    "Reviewer zaman aşımına uğradı; görev ve kanıtlar "
                    "korundu, komut başarısız sayılmadı."
                ),
            )
            return
        except Exception as exc:
            task.status = "rework_required"
            budget_exhausted = self._is_mission_budget_error(exc)
            if budget_exhausted:
                self._mark_task_blocked(
                    task=task,
                    recovery_reason="mission_budget_exhausted",
                    message=self._mission_budget_block_message(exc),
                )
                task.review_answer = task.blocked_reason
            else:
                task.recovery_reason = "reviewer_error"
                task.review_answer = f"{type(exc).__name__}: {exc}"
            self._clear_operation_if(command, f"review:{task.id}")
            self._event(
                command,
                type=(
                    "mission_budget_exhausted"
                    if budget_exhausted
                    else "review_error_recovered"
                ),
                task_id=task.id,
                message=task.review_answer,
            )
        await self._handle_reviewer_response(
            command=command,
            task=task,
            response=review,
        )
        self._clear_operation_if(command, f"review:{task.id}")
        self._refresh_task_states(command)
        await self.store.put(command)
        if command.auto_run and command.status not in {
            "completed",
            "failed",
            "awaiting_approval",
            "waiting_decision",
        }:
            self._spawn(
                self.advance(command_id=command.id, background=True),
                command_id=command.id,
                operation="auto_advance",
            )

    async def _handle_reviewer_response(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        response: AgentResponse,
    ) -> None:
        task.last_agent_response = response
        task.review_answer = response.answer

        if response.status == "awaiting_approval":
            self._set_pending_approval(
                command=command,
                task=task,
                response=response,
                phase="reviewer",
            )
            self._event(
                command,
                type="review_approval_required",
                task_id=task.id,
                message=(
                    f"{task.id} Reviewer doğrulaması için "
                    "yeni bir onay bekliyor."
                ),
            )
            return

        if response.status != "completed":
            task.status = "rework_required"
            self._clear_approval_payload(
                task,
                state="failed",
                message=(
                    "Reviewer model sınırı veya sağlayıcı hatası nedeniyle "
                    "karar veremedi; görev güvenli biçimde yeniden "
                    "çalıştırılabilir."
                ),
            )
            self._event(
                command,
                type="review_deferred",
                task_id=task.id,
                message=f"{task.id}: {response.answer}",
            )
            return

        if _ACCEPT.search(response.answer):
            task.status = "completed"
            self._clear_approval_payload(
                task,
                state="applied",
                message="Reviewer görevi kabul etti.",
            )
            command.handoffs.append(
                SupervisorHandoff(
                    id=secrets.token_urlsafe(8),
                    task_id=task.id,
                    type="review_accept",
                    from_agent="reviewer",
                    to_agent="supervisor",
                    summary=response.answer,
                    evidence=self._task_evidence(response),
                )
            )
            self._event(
                command,
                type="task_accepted",
                task_id=task.id,
                message=f"{task.id} Reviewer tarafından kabul edildi.",
            )
            await self._record_improvement_outcome(
                command=command,
                task=task,
                success=True,
            )
        elif _REJECT.search(response.answer):
            task.status = "rework_required"
            task.recovery_reason = "reviewer_rework"
            self._clear_approval_payload(
                task,
                state="applied",
                message="Reviewer somut revizyon istedi.",
            )
            command.handoffs.append(
                SupervisorHandoff(
                    id=secrets.token_urlsafe(8),
                    task_id=task.id,
                    type="review_reject",
                    from_agent="reviewer",
                    to_agent=task.assigned_agent,
                    summary=response.answer,
                    evidence=self._task_evidence(response),
                )
            )
            self._event(
                command,
                type="task_rejected",
                task_id=task.id,
                message=f"{task.id} yeniden çalışma gerektiriyor.",
            )
        else:
            task.status = "rework_required"
            self._clear_approval_payload(
                task,
                state="failed",
                message="Reviewer KABUL veya RET protokolünü tamamlamadı.",
            )
            self._event(
                command,
                type="review_protocol_failed",
                task_id=task.id,
                message=task.last_approval_message or "Review protokol hatası.",
            )

    async def _handle_worker_response(
        self,
        *,
        command: SupervisorCommand,
        task: SupervisorTask,
        response: AgentResponse,
    ) -> None:
        task.last_agent_response = response
        task.last_answer = response.answer

        if response.status == "awaiting_approval":
            self._set_pending_approval(
                command=command,
                task=task,
                response=response,
                phase="worker",
            )
            self._event(
                command,
                type="task_approval_required",
                task_id=task.id,
                message=(
                    f"{task.id} güvenli işlem {task.approval_version} "
                    "için kullanıcı onayı bekliyor."
                ),
                data={
                    "approval_id": task.approval_id,
                    "approval_version": task.approval_version,
                    "tool": task.approval_tool,
                },
            )
            return

        if response.status != "completed":
            if self.settings.supervisor_auto_evidence_reconcile:
                reconciled = await self._reconcile_task_evidence(
                    command=command,
                    task=task,
                    reason=f"agent_response:{response.status}",
                )
                if reconciled:
                    return

            ledger_has_applied_tools = bool(
                self._applied_tool_records(task)
            )
            if (
                self.settings.supervisor_recover_after_applied_tool
                and (
                    ledger_has_applied_tools
                    or self._has_applied_tool_evidence(response)
                )
            ):
                task.status = "rework_required"
                task.continuation_resumes += 1
                task.recovery_reason = "model_limit_with_ledger"
                self._clear_approval_payload(
                    task,
                    state="applied",
                    message=(
                        "Model/adım sınırına ulaşıldı fakat uygulanmış "
                        "işlemler korunuyor. Devam Et ile kanıtlar yeniden "
                        "uzlaştırılacak ve yalnızca eksik dosya veya "
                        "doğrulama tamamlanacak."
                    ),
                )
                self._event(
                    command,
                    type="task_recovery_ready",
                    task_id=task.id,
                    message=task.last_approval_message or "Devam gerekli.",
                    data={
                        "missing_files": task.reconciliation_missing_files,
                        "verification_found": (
                            task.reconciliation_verification_found
                        ),
                    },
                )
                return

            task.status = "failed"
            self._clear_approval_payload(
                task,
                state="failed",
                message=response.answer,
            )
            self._event(
                command,
                type="task_failed",
                task_id=task.id,
                message=response.answer,
            )
            return

        task.recovery_reason = None
        self._clear_approval_payload(
            task,
            state="applied",
            message="Agent görevi tamamladı; bağımsız inceleme başlıyor.",
        )
        command.handoffs.append(
            SupervisorHandoff(
                id=secrets.token_urlsafe(8),
                task_id=task.id,
                type="completion",
                from_agent=task.assigned_agent,
                to_agent="reviewer",
                summary=response.answer,
                evidence=self._task_evidence(response),
            )
        )

        if self.settings.supervisor_auto_review:
            await self._review(command=command, task=task)
        else:
            task.status = "completed"
            self._event(
                command,
                type="task_completed",
                task_id=task.id,
                message=f"{task.id} agent tarafından tamamlandı.",
            )

    async def _execute_prepared_task(
        self,
        *,
        command_id: str,
        task_id: str,
    ) -> SupervisorCommand:
        started_at = datetime.now(timezone.utc)
        operation = f"task:{task_id}"
        command = await self.store.get(command_id)
        task = next(
            (item for item in command.tasks if item.id == task_id),
            None,
        )
        if task is None:
            raise KeyError("Görev bulunamadı.")

        if command.recovery_status == "scheduled" and command.recovery_task_id == task.id:
            command.recovery_status = "running"
            await self.store.put(command)

        if task.exact_files:
            res_cmd = await self._advance_structured_task(
                command_id=command_id,
                task_id=task_id,
                reason="task_start",
            )
            completed_at = datetime.now(timezone.utc)
            task_ref = next((t for t in res_cmd.tasks if t.id == task_id), task)
            outcome = "succeeded" if task_ref.status in {"completed", "reviewing", "awaiting_approval"} else ("cancelled" if task_ref.status == "cancelled" else "failed")
            receipt = await self._record_execution_receipt(
                mission_id=command_id,
                execution_kind="worker" if task_ref.assigned_agent else "task",
                actor_kind="worker",
                actor_id=task_ref.assigned_agent or "supervisor",
                worker_role=task_ref.assigned_agent or "supervisor",
                task_id=task_ref.id,
                started_at=started_at,
                completed_at=completed_at,
                outcome=outcome,
                request_summary=f"Execution of task '{task_ref.title}'",
                affected_files=task_ref.exact_files or [],
            )
            if outcome == "failed":
                if res_cmd.recovery_status in {"scheduled", "running"} and res_cmd.recovery_task_id == task_ref.id:
                    self._event(
                        res_cmd,
                        type="mission_recovery_failed",
                        task_id=task_ref.id,
                        message="Mission recovery execution failed.",
                        data={
                            "failure_id": res_cmd.latest_failure.failure_id if res_cmd.latest_failure else "unknown",
                            "task_id": task_ref.id,
                            "category": res_cmd.latest_failure.category if res_cmd.latest_failure else "unknown",
                            "recovery_attempts_for_failure": res_cmd.recovery_attempts_for_failure,
                            "recovery_count": res_cmd.recovery_count,
                            "recovery_checkpoint_id": res_cmd.recovery_checkpoint_id,
                            "control_version": res_cmd.control_version,
                            "scheduled": False,
                        },
                    )
                await self._record_mission_failure(
                    command=res_cmd,
                    phase="verification" if task_ref.verification_failures else "task_execution",
                    error_code="verification_failed" if task_ref.verification_failures else "internal_error",
                    safe_message=task_ref.last_approval_message or "Structured task execution failed.",
                    task=task_ref,
                    source_receipt_id=receipt.receipt_id,
                    receipt_outcome=outcome,
                    verification_failed=bool(task_ref.verification_failures),
                )
            else:
                await self._finalize_mission_recovery_if_needed(command=res_cmd, task=task_ref)
            return res_cmd

        request = AgentRequest(
            message=self._assignment_prompt(command, task),
            agent_id=task.assigned_agent,
            routing_mode="auto",
            max_steps=self.settings.supervisor_task_agent_max_steps,
            max_model_calls=(
                self.settings.supervisor_task_agent_max_model_calls
            ),
            supervised_budget=True,
            include_trace=True,
            allow_deterministic_tools=False,
            additional_write_paths=task.exact_files,
            exclusive_write_paths=task.exact_files,
            applied_tool_fingerprints=(
                self._applied_tool_fingerprints(task)
            ),
            usage_scope=command_id,
            usage_task_id=task.id,
        )

        failure_code: str | None = None
        failure_exception: BaseException | None = None
        try:
            response = await self._await_with_heartbeat(
                self.agent.run(request),
                command_id=command_id,
                timeout_seconds=(
                    self.settings.supervisor_task_agent_timeout_seconds
                ),
                heartbeat_message=(
                    f"{task.assigned_agent} {task.id} üzerinde çalışıyor; "
                    "model/araç cevabı bekleniyor."
                ),
                heartbeat_phase="agent_work",
            )
        except asyncio.CancelledError:
            completed_at = datetime.now(timezone.utc)
            await self._record_execution_receipt(
                mission_id=command_id,
                execution_kind="worker" if task.assigned_agent else "task",
                actor_kind="worker",
                actor_id=task.assigned_agent or "supervisor",
                worker_role=task.assigned_agent or "supervisor",
                task_id=task.id,
                started_at=started_at,
                completed_at=completed_at,
                outcome="cancelled",
                request_summary=f"Execution of task '{task.title}'",
                affected_files=task.exact_files or [],
                error_code="task_cancelled",
            )
            raise
        except TimeoutError as exc:
            failure_code = "timeout"
            failure_exception = exc
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            reconciled = False
            if self.settings.supervisor_auto_evidence_reconcile:
                reconciled = await self._reconcile_task_evidence(
                    command=command,
                    task=task,
                    reason="initial_agent_timeout",
                )
            if not reconciled:
                task.status = "rework_required"
                task.recovery_reason = "task_agent_timeout"
                task.last_approval_message = (
                    "Agent yanıt süresi doldu. Değişiklikler revert edildi."
                )
                self._event(
                    command,
                    type="task_agent_timeout_recovered",
                    task_id=task.id,
                    message=task.last_approval_message,
                )
        except Exception as exc:
            failure_exception = exc
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            reconciled = False
            if self.settings.supervisor_auto_evidence_reconcile:
                reconciled = await self._reconcile_task_evidence(
                    command=command,
                    task=task,
                    reason=f"initial_agent_error:{type(exc).__name__}",
                )
            if not reconciled:
                budget_exhausted = self._is_mission_budget_error(exc)
                if budget_exhausted:
                    failure_code = "budget_exhausted"
                    self._mark_task_blocked(
                        task=task,
                        recovery_reason="mission_budget_exhausted",
                        message=self._mission_budget_block_message(exc),
                    )
                else:
                    failure_code = "internal_error"
                    task.status = "rework_required"
                    task.recovery_reason = "task_agent_error"
                    task.last_approval_message = (
                        f"Agent çağrısı güvenli biçimde durduruldu: "
                        f"{type(exc).__name__}: {exc}"
                    )
                self._event(
                    command,
                    type=(
                        "mission_budget_exhausted"
                        if budget_exhausted
                        else "task_agent_error_recovered"
                    ),
                    task_id=task.id,
                    message=task.last_approval_message,
                )
        else:
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            await self._handle_worker_response(
                command=command,
                task=task,
                response=response,
            )

        if failure_code is None and task.status == "failed":
            failure_code = "internal_error"
        elif (
            failure_code is None
            and task.status == "rework_required"
            and task.verification_failures > 0
        ):
            failure_code = "verification_failed"

        self._clear_operation_if(command, operation)
        self._refresh_task_states(command)
        await self.store.put(command)

        completed_at = datetime.now(timezone.utc)
        outcome = "succeeded" if task.status in {"completed", "reviewing", "awaiting_approval"} else ("cancelled" if task.status == "cancelled" else "failed")
        receipt = await self._record_execution_receipt(
            mission_id=command_id,
            execution_kind="worker" if task.assigned_agent else "task",
            actor_kind="worker",
            actor_id=task.assigned_agent or "supervisor",
            worker_role=task.assigned_agent or "supervisor",
            task_id=task.id,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
            request_summary=f"Execution of task '{task.title}'",
            affected_files=task.exact_files or [],
        )

        if outcome == "failed" and failure_code is not None:
            if command.recovery_status in {"scheduled", "running"} and command.recovery_task_id == task.id:
                self._event(
                    command,
                    type="mission_recovery_failed",
                    task_id=task.id,
                    message="Mission recovery execution failed.",
                    data={
                        "failure_id": command.latest_failure.failure_id if command.latest_failure else "unknown",
                        "task_id": task.id,
                        "category": command.latest_failure.category if command.latest_failure else "unknown",
                        "recovery_attempts_for_failure": command.recovery_attempts_for_failure,
                        "recovery_count": command.recovery_count,
                        "recovery_checkpoint_id": command.recovery_checkpoint_id,
                        "control_version": command.control_version,
                        "scheduled": False,
                    },
                )
            await self._record_mission_failure(
                command=command,
                phase="task_execution",
                error_code=failure_code,
                safe_message=task.last_approval_message or "Task execution failed.",
                task=task,
                source_receipt_id=receipt.receipt_id,
                exception=failure_exception,
                receipt_outcome=outcome,
            )
        else:
            await self._finalize_mission_recovery_if_needed(command=command, task=task)

        return command

    async def run_task(
        self,
        *,
        command_id: str,
        task_id: str,
        background: bool = False,
    ) -> SupervisorCommand:
        operation = f"task:{task_id}"
        execute_sync = False

        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            self._refresh_task_states(command)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is None:
                raise KeyError("Görev bulunamadı.")

            active = self._active_task(
                command,
                exclude_task_id=task_id,
            )
            if self.settings.supervisor_single_active_task and active:
                raise ValueError(
                    f"Önce aktif {active.id} görevini tamamla veya "
                    "onayını sonuçlandır. Paylaşılan workspace üzerinde "
                    "aynı anda yalnızca bir görev çalıştırılır."
                )

            if task.status in {"running", "reviewing", "awaiting_approval"}:
                return command

            recoverable_failed = (
                task.status == "failed"
                and bool(self._applied_tool_records(task))
            )
            if task.status not in {"ready", "rework_required"} and not recoverable_failed:
                raise ValueError(
                    f"{task.id} şu anda çalıştırılamaz: {task.status}"
                )

            self._capture_snapshot_if_needed(command, task)

            focused_protocol_changed = (
                self._reconcile_focused_generation_revision(
                    command=command,
                    task=task,
                )
            )
            runtime_changed = self._reconcile_terminal_runtime_revision(
                command=command,
                task=task,
            )
            environment_changed = self._reconcile_environment_revision(
                command=command,
                task=task,
            )
            if focused_protocol_changed or runtime_changed or environment_changed:
                await self.store.put(command)

            hard_blocked = task.recovery_reason in {
                "repeated_failure_blocked",
                "external_prerequisite_blocked",
                "planning_contract_incomplete",
                "focused_completion_without_evidence",
                "focused_protocol_failed",
                "focused_route_unavailable",
                "focused_step_error",
                "focused_output_quality",
                "mission_budget_exhausted",
                "tdd_self_fix_exhausted",
            }
            if (
                hard_blocked
                and task.blocked_state_token
                and task.blocked_state_token == self._task_state_token(task)
            ):
                already_recorded = any(
                    event.type == "resume_ignored_no_state_change"
                    and event.task_id == task.id
                    and event.data.get("state_token")
                    == task.blocked_state_token
                    for event in reversed(command.events)
                )
                if not already_recorded:
                    self._event(
                        command,
                        type="resume_ignored_no_state_change",
                        task_id=task.id,
                        message=(
                            "Görev engellendikten sonra workspace, araç zinciri "
                            "veya terminal runtime değişmedi. Aynı işlem yeniden "
                            "başlatılmadı."
                        ),
                        data={"state_token": task.blocked_state_token},
                    )
                    self._refresh_task_states(command)
                    await self.store.put(command)
                return command

            if (
                self.settings.supervisor_auto_evidence_reconcile
                and task.status in {"rework_required", "failed"}
            ):
                reconciled = await self._reconcile_task_evidence(
                    command=command,
                    task=task,
                    reason="manual_or_automatic_resume",
                )
                if reconciled:
                    self._clear_operation_if(command, operation)
                    self._refresh_task_states(command)
                    await self.store.put(command)
                    return command
                task.status = "rework_required"

            continuation_resume = (
                task.status == "rework_required"
                and task.recovery_reason in {
                    "continuation_timeout",
                    "model_limit_after_tool",
                    "model_limit_with_ledger",
                    "evidence_incomplete",
                    "task_agent_timeout",
                    "task_agent_error",
                    "task_watchdog_timeout",
                    "task_watchdog_timeout_with_evidence",
                    "background_operation_interrupted",
                }
            )
            if continuation_resume:
                task.continuation_resumes += 1
            else:
                if task.attempts >= self.settings.supervisor_max_task_attempts:
                    task.status = "failed"
                    raise ValueError(
                        f"{task.id} maksimum deneme sayısına ulaştı."
                    )
                task.attempts += 1

            task.recovery_reason = None
            task.status = "running"
            command.status = "running"
            command.failure_reason = None
            self._set_operation(
                command,
                operation=operation,
                phase="agent_work",
                message=f"{task.assigned_agent} {task.id} üzerinde çalışıyor.",
                attempt=task.attempts,
                max_attempts=self.settings.supervisor_max_task_attempts,
                route="auto",
                reset_started_at=True,
            )
            self._clear_approval_payload(task, state="idle")

            command.handoffs.append(
                SupervisorHandoff(
                    id=secrets.token_urlsafe(8),
                    task_id=task.id,
                    type=("rework" if continuation_resume else "task_assignment"),
                    from_agent="supervisor",
                    to_agent=task.assigned_agent,
                    summary=self._assignment_prompt(command, task),
                )
            )
            self._event(
                command,
                type="task_started",
                task_id=task.id,
                message=(
                    f"{task.id}, {task.assigned_agent} agentına atandı "
                    + (
                        f"(kurtarma {task.continuation_resumes})."
                        if continuation_resume
                        else f"(deneme {task.attempts})."
                    )
                ),
                data={
                    "agent": task.assigned_agent,
                    "continuation_resume": continuation_resume,
                    "single_active_task": (
                        self.settings.supervisor_single_active_task
                    ),
                },
            )
            await self.store.put(command)

            if background:
                spawned = self._spawn(
                    self._execute_prepared_task(
                        command_id=command.id,
                        task_id=task.id,
                    ),
                    command_id=command.id,
                    operation=operation,
                )
                if not spawned:
                    return command
                return command
            execute_sync = True

        if execute_sync:
            return await self._execute_prepared_task(
                command_id=command_id,
                task_id=task_id,
            )
        return await self.store.get(command_id)

    async def advance(
        self,
        *,
        command_id: str,
        max_tasks: int = 1,
        background: bool = False,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        self._refresh_task_states(command)

        active = self._active_task(command)
        if self.settings.supervisor_single_active_task and active:
            return command

        if command.status == "waiting_decision":
            raise ValueError(
                "Komut kullanıcı kararlarını bekliyor."
            )
        if command.status in {"completed", "failed", "awaiting_approval"}:
            return command

        if background:
            ready = next(
                (
                    task
                    for task in command.tasks
                    if task.status in {"ready", "rework_required"}
                ),
                None,
            )
            if ready is None:
                return command
            return await self.run_task(
                command_id=command.id,
                task_id=ready.id,
                background=True,
            )

        executed = 0
        while executed < max_tasks:
            self._refresh_task_states(command)
            ready = next(
                (
                    task
                    for task in command.tasks
                    if task.status in {"ready", "rework_required"}
                ),
                None,
            )
            if ready is None:
                break

            command = await self.run_task(
                command_id=command.id,
                task_id=ready.id,
                background=False,
            )
            executed += 1

            if command.status in {
                "awaiting_approval",
                "failed",
                "waiting_decision",
            }:
                break

        return command

    async def _recover_continuation_failure(
        self,
        *,
        command_id: str,
        task_id: str,
        session_id: str,
        approval_id: str,
        approval_version: int,
        reason: str,
        event_type: str,
    ) -> SupervisorCommand:
        if hasattr(self.agent, "abandon_session"):
            await self.agent.abandon_session(session_id)

        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is None:
                raise KeyError("Görev bulunamadı.")

            task.status = "rework_required"
            task.continuation_resumes += 1
            task.recovery_reason = "evidence_incomplete"
            task.agent_session_id = None
            task.approval_id = None
            task.approval_phase = None
            task.approval_tool = None
            task.approval_description = None
            task.approval_preview = None
            task.approval_expires_at = None
            task.processing_approval_id = None
            task.approval_state = "applied"
            task.last_approval_message = (
                f"Güvenli işlem {approval_version} başarıyla uygulandı. "
                "Model devamı tamamlanamadı; araç tekrar çalıştırılmadan "
                "kalan işten devam edilebilir. "
                f"Neden: {reason}"
            )
            self._upsert_approval_record(
                task,
                approval_id=approval_id,
                approval_version=approval_version,
                phase="worker",
                state="applied",
                message=task.last_approval_message,
                finished_at=utc_now(),
            )
            command.failure_reason = None
            self._clear_operation(command)
            self._event(
                command,
                type=event_type,
                task_id=task.id,
                message=task.last_approval_message,
                data={
                    "approval_id": approval_id,
                    "approval_version": approval_version,
                    "recovery": "rework_without_replaying_tool",
                },
            )
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

    async def _block_continuation_for_mission_budget(
        self,
        *,
        command_id: str,
        task_id: str,
        session_id: str,
        exc: Exception,
    ) -> SupervisorCommand:
        if hasattr(self.agent, "abandon_session"):
            await self.agent.abandon_session(session_id)
        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            task.agent_session_id = None
            self._mark_task_blocked(
                task=task,
                recovery_reason="mission_budget_exhausted",
                message=self._mission_budget_block_message(exc),
            )
            self._clear_operation(command)
            self._event(
                command,
                type="mission_budget_exhausted",
                task_id=task.id,
                message=task.last_approval_message,
            )
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

    async def _complete_approval_transaction(
        self,
        *,
        command_id: str,
        task_id: str,
        session_id: str,
        approval_id: str,
        approval_version: int,
        phase: str,
    ) -> SupervisorCommand:
        command = await self.store.get(command_id)
        task = next(
            (item for item in command.tasks if item.id == task_id),
            None,
        )
        if task is None:
            raise KeyError("Görev bulunamadı.")

        preview_timeout = 0.0
        if isinstance(task.approval_preview, dict):
            raw_timeout = task.approval_preview.get("timeout_seconds")
            if isinstance(raw_timeout, (int, float)):
                preview_timeout = float(raw_timeout)

        tool_timeout = max(
            self.settings.supervisor_approval_tool_timeout_seconds,
            preview_timeout + 20.0,
        )

        legacy_response = None
        supervisor_direct = self._is_supervisor_session(session_id)
        try:
            if supervisor_direct:
                direct_result = await self._await_with_heartbeat(
                    self.tools.execute_approved(approval_id),
                    command_id=command_id,
                    timeout_seconds=tool_timeout,
                    heartbeat_message=(
                        f"Güvenli işlem {approval_version} uygulanıyor; "
                        "yerel araç sonucu bekleniyor."
                    ),
                    heartbeat_phase="deterministic_tool_execution",
                )
                from types import SimpleNamespace
                application = SimpleNamespace(
                    success=True,
                    tool_name=task.approval_tool or "approved_tool",
                    result=direct_result,
                )
            elif hasattr(self.agent, "apply_approval"):
                application = await self._await_with_heartbeat(
                    self.agent.apply_approval(
                        session_id=session_id,
                        approval_id=approval_id,
                    ),
                    command_id=command_id,
                    timeout_seconds=tool_timeout,
                    heartbeat_message=(
                        f"Güvenli işlem {approval_version} uygulanıyor; "
                        "araç sonucu bekleniyor."
                    ),
                    heartbeat_phase="applying_approved_tool",
                )
            else:
                # Compatibility adapter for external AgentEngine
                # implementations that still expose atomic approve().
                legacy_response = await self._await_with_heartbeat(
                    self.agent.approve(
                        session_id=session_id,
                        approval_id=approval_id,
                    ),
                    command_id=command_id,
                    timeout_seconds=tool_timeout,
                    heartbeat_message=(
                        f"Güvenli işlem {approval_version} uygulanıyor."
                    ),
                    heartbeat_phase="legacy_approval",
                )
                from types import SimpleNamespace
                application = SimpleNamespace(
                    success=True,
                    tool_name=task.approval_tool or "approved_tool",
                    result={"legacy_atomic_approval": True},
                )
        except Exception as exc:
            async with self._command_lock(command_id):
                command = await self.store.get(command_id)
                task = next(
                    (item for item in command.tasks if item.id == task_id),
                    None,
                )
                if task is None:
                    raise KeyError("Görev bulunamadı.")

                task.last_consumed_approval_id = approval_id
                task.status = "rework_required"
                self._upsert_approval_record(
                    task,
                    approval_id=approval_id,
                    approval_version=approval_version,
                    phase=phase,
                    state="failed",
                    message=(
                        "Onaylanan güvenli işlemin sonucu doğrulanamadı: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    finished_at=utc_now(),
                )
                self._clear_approval_payload(
                    task,
                    state="failed",
                    message=(
                        "Araç sonucu doğrulanamadı. Aynı işlem otomatik "
                        "tekrarlanmayacak; Devam Et ile workspace yeniden "
                        f"incelenecek. Neden: {type(exc).__name__}: {exc}"
                    ),
                )
                self._clear_operation(command)
                self._event(
                    command,
                    type="approval_tool_application_failed",
                    task_id=task.id,
                    message=task.last_approval_message or "Onay hatası.",
                    data={
                        "approval_id": approval_id,
                        "approval_version": approval_version,
                    },
                )
                self._refresh_task_states(command)
                await self.store.put(command)
                return command

        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is None:
                raise KeyError("Görev bulunamadı.")

            task.last_consumed_approval_id = approval_id
            task.processing_approval_id = None
            effective_success = self._effective_tool_success(
                application.tool_name,
                application.success,
                application.result,
            )
            if command.autonomy_mode == "task":
                task.autonomy_granted = True

            if not application.success:
                task.status = "rework_required"
                task.approval_state = "failed"
                task.last_approval_message = (
                    f"Güvenli işlem {approval_version} çalıştırıldı fakat "
                    f"başarısız oldu: {application.result}"
                )
                self._upsert_approval_record(
                    task,
                    approval_id=approval_id,
                    approval_version=approval_version,
                    phase=phase,
                    state="failed",
                    message=task.last_approval_message,
                    finished_at=utc_now(),
                    success=False,
                    result=application.result,
                )
                task.agent_session_id = None
                task.approval_id = None
                task.approval_phase = None
                task.approval_tool = None
                task.approval_description = None
                task.approval_preview = None
                task.approval_expires_at = None
                if hasattr(self.agent, "abandon_session"):
                    await self.agent.abandon_session(session_id)
                self._clear_operation(command)
                self._event(
                    command,
                    type="approval_tool_result_failed",
                    task_id=task.id,
                    message=task.last_approval_message,
                )
                self._refresh_task_states(command)
                await self.store.put(command)
                return command

            task.approval_state = "applied"
            task.last_approval_message = (
                f"Güvenli işlem {approval_version} uygulandı. "
                + (
                    "Araç sonucu başarılı; kalan adım belirleniyor."
                    if effective_success
                    else "Araç çalıştı fakat doğrulama başarısız; "
                    "Prometheus yeni bir strateji seçecek."
                )
            )
            self._upsert_approval_record(
                task,
                approval_id=approval_id,
                approval_version=approval_version,
                phase=phase,
                state="applied",
                message=task.last_approval_message,
                finished_at=utc_now(),
                success=effective_success,
                result=application.result,
            )
            task.approval_id = None
            task.approval_tool = None
            task.approval_description = None
            task.approval_preview = None
            task.approval_expires_at = None
            task.status = "running"
            command.status = "running"
            self._set_operation(
                command,
                operation=f"continuation:{task.id}",
                phase="agent_continuation",
                message=(
                    f"Güvenli işlem {approval_version} uygulandı; "
                    "model yalnızca sonraki adımı hazırlıyor."
                ),
                attempt=approval_version,
                route="continuation",
                reset_started_at=True,
            )
            self._event(
                command,
                type="approval_tool_checkpointed",
                task_id=task.id,
                message=task.last_approval_message,
                data={
                    "approval_id": approval_id,
                    "approval_version": approval_version,
                    "tool": application.tool_name,
                    "success": effective_success,
                },
            )
            if (
                application.tool_name == "workspace_write"
                and isinstance(application.result, dict)
            ):
                self._record_materialized_file(
                    task,
                    application.result.get("path"),
                )
            await self.store.put(command)

        if phase == "worker" and task.exact_files:
            if (
                not supervisor_direct
                and hasattr(self.agent, "abandon_session")
            ):
                await self.agent.abandon_session(session_id)
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            task.agent_session_id = None
            return await self._advance_structured_task(
                command_id=command_id,
                task_id=task_id,
                reason=(
                    f"approved_tool:{application.tool_name}"
                ),
                last_tool_name=application.tool_name,
                last_result=application.result,
            )

        if phase == "worker":
            completion = await self._local_completion_response(
                task=task,
                tool_name=application.tool_name,
                result=application.result,
            )
            if completion is not None:
                if hasattr(self.agent, "abandon_session"):
                    await self.agent.abandon_session(session_id)
                command = await self.store.get(command_id)
                task = next(
                    item for item in command.tasks if item.id == task_id
                )
                task.agent_session_id = None
                task.recovery_reason = None
                await self._handle_worker_response(
                    command=command,
                    task=task,
                    response=completion,
                )
                async with self._command_lock(command_id):
                    if task.status not in {
                        "awaiting_approval", "running", "reviewing"
                    }:
                        self._clear_operation(command)
                    self._refresh_task_states(command)
                    await self.store.put(command)
                    return command

        try:
            if legacy_response is not None:
                response = legacy_response
            else:
                if hasattr(self.agent, "abandon_session"):
                    await self.agent.abandon_session(session_id)
                command = await self.store.get(command_id)
                task = next(
                    item for item in command.tasks
                    if item.id == task_id
                )
                task.agent_session_id = None
                response = await self._await_with_heartbeat(
                    self.agent.run(
                        AgentRequest(
                            message=self._assignment_prompt(
                                command,
                                task,
                            ),
                            agent_id=task.assigned_agent,
                            routing_mode="auto",
                            max_steps=(
                                self.settings
                                .supervisor_task_agent_max_steps
                            ),
                            max_model_calls=(
                                self.settings
                                .supervisor_task_agent_max_model_calls
                            ),
                            supervised_budget=True,
                            include_trace=True,
                            allow_deterministic_tools=False,
                            additional_write_paths=task.exact_files,
                            exclusive_write_paths=task.exact_files,
                            applied_tool_fingerprints=(
                                self._applied_tool_fingerprints(task)
                            ),
                            usage_scope=command_id,
                            usage_task_id=task.id,
                        )
                    ),
                    command_id=command_id,
                    timeout_seconds=(
                        self.settings
                        .supervisor_fresh_recovery_timeout_seconds
                    ),
                    heartbeat_message=(
                        f"Güvenli işlem {approval_version} tamamlandı; "
                        "temiz agent oturumu yalnızca eksik işi hazırlıyor."
                    ),
                    heartbeat_phase="fresh_agent_recovery",
                )
        except TimeoutError as exc:
            return await self._recover_continuation_failure(
                command_id=command_id,
                task_id=task_id,
                session_id=session_id,
                approval_id=approval_id,
                approval_version=approval_version,
                reason=str(exc),
                event_type="approval_continuation_timeout_recovered",
            )
        except Exception as exc:
            if self._is_mission_budget_error(exc):
                return await self._block_continuation_for_mission_budget(
                    command_id=command_id,
                    task_id=task_id,
                    session_id=session_id,
                    exc=exc,
                )
            return await self._recover_continuation_failure(
                command_id=command_id,
                task_id=task_id,
                session_id=session_id,
                approval_id=approval_id,
                approval_version=approval_version,
                reason=f"{type(exc).__name__}: {exc}",
                event_type="approval_continuation_error_recovered",
            )

        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is None:
                raise KeyError("Görev bulunamadı.")
            task.agent_session_id = None

        if phase == "worker":
            await self._handle_worker_response(
                command=command,
                task=task,
                response=response,
            )
        else:
            await self._handle_reviewer_response(
                command=command,
                task=task,
                response=response,
            )

        async with self._command_lock(command_id):
            if task.status not in {
                "awaiting_approval",
                "running",
                "reviewing",
            }:
                self._clear_operation(command)
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

    async def _complete_approval_transaction_and_resume(
        self,
        *,
        command_id: str,
        task_id: str,
        session_id: str,
        approval_id: str,
        approval_version: int,
        phase: str,
    ) -> SupervisorCommand:
        command = await self._complete_approval_transaction(
            command_id=command_id,
            task_id=task_id,
            session_id=session_id,
            approval_id=approval_id,
            approval_version=approval_version,
            phase=phase,
        )
        if command.auto_run and command.status == "ready":
            return await self.advance(
                command_id=command.id,
                max_tasks=self.settings.supervisor_auto_run_max_tasks,
            )
        return command

    async def approve(
        self,
        *,
        command_id: str,
        task_id: str,
        expected_approval_id: str | None = None,
        expected_approval_version: int | None = None,
        background: bool | None = None,
    ) -> SupervisorCommand:
        if background is None:
            background = self.settings.supervisor_approval_background

        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is None:
                raise KeyError("Görev bulunamadı.")

            supplied_id = expected_approval_id or task.approval_id
            supplied_version = (
                expected_approval_version
                if expected_approval_version is not None
                else task.approval_version
            )

            if (
                supplied_id
                and supplied_id == task.last_consumed_approval_id
            ):
                self._event(
                    command,
                    type="approval_duplicate_ignored",
                    task_id=task.id,
                    message=(
                        "Aynı onay ikinci kez gönderildi; araç yeniden "
                        "çalıştırılmadan güncel durum döndürüldü."
                    ),
                )
                await self.store.put(command)
                return command

            if task.approval_state == "processing":
                self._event(
                    command,
                    type="approval_already_processing",
                    task_id=task.id,
                    message="Onay işlemi zaten uygulanıyor.",
                )
                await self.store.put(command)
                return command

            next_approval = self._next_pending_approval(command)
            if (
                next_approval is not None
                and next_approval.id != task.id
            ):
                self._event(
                    command,
                    type="approval_out_of_order_blocked",
                    task_id=task.id,
                    message=(
                        f"Önce {next_approval.id} görevindeki "
                        f"{next_approval.approval_version}. güvenli işlem "
                        "tamamlanmalı."
                    ),
                    data={"next_task_id": next_approval.id},
                )
                await self.store.put(command)
                raise ValueError(
                    f"Onay sırası: önce {next_approval.id} görevindeki "
                    f"{next_approval.approval_version}. güvenli işlemi "
                    "tamamla."
                )

            if (
                task.status != "awaiting_approval"
                or not task.agent_session_id
                or not task.approval_id
                or not task.approval_phase
            ):
                raise ValueError("Bu görev onay beklemiyor.")

            if (
                supplied_id != task.approval_id
                or supplied_version != task.approval_version
            ):
                self._event(
                    command,
                    type="approval_stale_ignored",
                    task_id=task.id,
                    message=(
                        "Eski bir onay kartı gönderildi; güvenlik için "
                        "çalıştırılmadı ve güncel kart döndürüldü."
                    ),
                    data={
                        "submitted_id": supplied_id,
                        "current_id": task.approval_id,
                        "submitted_version": supplied_version,
                        "current_version": task.approval_version,
                    },
                )
                await self.store.put(command)
                return command

            session_id = task.agent_session_id
            approval_id = task.approval_id
            approval_version = task.approval_version
            phase = task.approval_phase

            task.approval_state = "processing"
            task.processing_approval_id = approval_id
            task.last_approval_message = (
                f"Güvenli işlem {approval_version} uygulanıyor."
            )
            self._upsert_approval_record(
                task,
                approval_id=approval_id,
                approval_version=approval_version,
                phase=phase,
                state="processing",
                tool=task.approval_tool,
                description=task.approval_description,
                preview=task.approval_preview,
                message=task.last_approval_message,
                started_at=utc_now(),
            )
            task.status = "running"
            command.status = "running"
            self._set_operation(
                command,
                operation=f"approval:{task.id}",
                phase="applying_approval",
                message=task.last_approval_message,
                attempt=approval_version,
                reset_started_at=True,
            )
            self._event(
                command,
                type="approval_transaction_started",
                task_id=task.id,
                message=task.last_approval_message,
                data={
                    "approval_id": approval_id,
                    "approval_version": approval_version,
                },
            )
            await self.store.put(command)

        coroutine = self._complete_approval_transaction_and_resume(
            command_id=command_id,
            task_id=task_id,
            session_id=session_id,
            approval_id=approval_id,
            approval_version=approval_version,
            phase=phase,
        )
        if background:
            self._spawn(
                coroutine,
                command_id=command_id,
                operation=f"approval:{task_id}",
            )
            return command
        return await coroutine

    async def reject(
        self,
        *,
        command_id: str,
        task_id: str,
        expected_approval_id: str | None = None,
        expected_approval_version: int | None = None,
    ) -> SupervisorCommand:
        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                (item for item in command.tasks if item.id == task_id),
                None,
            )
            if task is None:
                raise KeyError("Görev bulunamadı.")

            supplied_id = expected_approval_id or task.approval_id
            supplied_version = (
                expected_approval_version
                if expected_approval_version is not None
                else task.approval_version
            )
            if (
                supplied_id
                and supplied_id == task.last_consumed_approval_id
            ):
                return command
            if task.approval_state == "processing":
                raise ValueError(
                    "Onay uygulanırken reddetme işlemi yapılamaz."
                )

            next_approval = self._next_pending_approval(command)
            if (
                next_approval is not None
                and next_approval.id != task.id
            ):
                raise ValueError(
                    f"Onay sırası: önce {next_approval.id} görevindeki "
                    f"{next_approval.approval_version}. güvenli işlemi "
                    "tamamla."
                )

            if (
                task.status != "awaiting_approval"
                or not task.agent_session_id
                or not task.approval_id
            ):
                raise ValueError("Bu görev onay beklemiyor.")
            if (
                supplied_id != task.approval_id
                or supplied_version != task.approval_version
            ):
                self._event(
                    command,
                    type="approval_stale_ignored",
                    task_id=task.id,
                    message="Eski onay kartı reddedilmeden güncel durum döndürüldü.",
                )
                await self.store.put(command)
                return command

            session_id = task.agent_session_id
            approval_id = task.approval_id

        if self._is_supervisor_session(session_id):
            await self.tools.reject_approval(approval_id)
            response = None
        else:
            response = await self.agent.reject(
                session_id=session_id,
                approval_id=approval_id,
            )

        async with self._command_lock(command_id):
            command = await self.store.get(command_id)
            task = next(
                item for item in command.tasks if item.id == task_id
            )
            if response is not None:
                task.last_agent_response = response
                task.last_answer = response.answer
            task.last_consumed_approval_id = approval_id
            task.status = "rework_required"
            self._upsert_approval_record(
                task,
                approval_id=approval_id,
                approval_version=supplied_version,
                phase=task.approval_phase or "worker",
                state="rejected",
                tool=task.approval_tool,
                description=task.approval_description,
                preview=task.approval_preview,
                message="İşlem kullanıcı tarafından reddedildi.",
                finished_at=utc_now(),
            )
            self._clear_approval_payload(
                task,
                state="rejected",
                message=(
                    "İşlem reddedildi; görev güvenli biçimde revizyon "
                    "kuyruğuna alındı."
                ),
            )
            self._event(
                command,
                type="approval_rejected",
                task_id=task.id,
                message=task.last_approval_message or "İşlem reddedildi.",
            )
            self._clear_operation(command)
            self._refresh_task_states(command)
            await self.store.put(command)
            return command

    async def preview_project_run(
        self,
        request: ProjectRunPreviewRequest,
    ) -> ProjectRunPreviewResponse:
        policy = WorkspacePolicy(
            root=self.settings.workspace_root,
            max_file_bytes=self.settings.workspace_max_file_bytes,
            max_search_results=self.settings.workspace_max_search_results,
        )

        try:
            resolved_path = policy.resolve(request.workspace_path, must_exist=False)
            policy.ensure_not_sensitive(resolved_path)
            rel_path = resolved_path.relative_to(policy.root).as_posix()
        except (ToolError, ValueError, OSError) as exc:
            raise ValueError(f"Geçersiz veya korumalı workspace yolu: {exc}") from exc

        try:
            result = await self.planning_kernel.build(goal=request.goal)
        except Exception as exc:
            raise ValueError(f"Deterministik önizleme derlemesi başarısız: {exc}") from exc

        known_paths = await self._known_paths()
        integrity = validate_planning_document(
            result.document,
            known_paths=known_paths,
            known_agents=set(self.agents.ids()),
        )
        if not integrity.valid:
            raise ValueError(
                "Plan doğrulaması başarısız: " + " | ".join(integrity.errors)
            )

        preview_tasks: list[ProjectRunPreviewTask] = []
        all_exact_files: list[str] = []
        all_verifications: list[str] = []

        for task in result.document.tasks:
            task_exact_files: list[str] = []
            candidate_files = list(task.exact_files)
            if not candidate_files:
                for ev in task.evidence:
                    ev_type = getattr(ev, "type", "") if not isinstance(ev, dict) else ev.get("type", "")
                    ev_val = getattr(ev, "value", "") if not isinstance(ev, dict) else ev.get("value", "")
                    if ev_type in {"file", "path"} and ev_val:
                        candidate_files.append(ev_val)

            if not candidate_files:
                for kp in sorted(known_paths):
                    if kp in task.title or kp in request.goal:
                        candidate_files.append(kp)

            for raw_path in candidate_files:
                try:
                    p = policy.resolve(raw_path, must_exist=False)
                    policy.ensure_not_sensitive(p)
                    rel_f = p.relative_to(policy.root).as_posix()
                    if rel_f and rel_f not in task_exact_files:
                        task_exact_files.append(rel_f)
                except Exception as exc:
                    raise ValueError(
                        f"Görev adımı geçersiz exact file yolu içeriyor '{raw_path}': {exc}"
                    ) from exc

            if not task_exact_files:
                raise ValueError(
                    f"Görev adımı '{task.title}' en az bir exact file scope taşımalıdır."
                )

            verification_cmd = (task.verification or "").strip()
            if not verification_cmd:
                raise ValueError(
                    f"Görev adımı '{task.title}' bir doğrulama komutu taşımalıdır."
                )

            preview_tasks.append(
                ProjectRunPreviewTask(
                    title=task.title,
                    assigned_agent=task.assigned_agent,
                    exact_files=task_exact_files,
                    verification=verification_cmd,
                    acceptance_criteria=list(task.acceptance_criteria),
                )
            )

            for f in task_exact_files:
                if f not in all_exact_files:
                    all_exact_files.append(f)
            if verification_cmd not in all_verifications:
                all_verifications.append(verification_cmd)

        warnings_list = list(integrity.warnings) if integrity.warnings else []
        warnings_list.append(
            "Preview is side-effect-free and does not execute commands or modify files."
        )
        warnings_list.append(
            "Exact user approval will be required before any execution."
        )

        res = ProjectRunPreviewResponse(
            goal=request.goal,
            workspace_path=rel_path if rel_path else ".",
            tasks=preview_tasks,
            exact_files=all_exact_files,
            verification_commands=all_verifications,
            warnings=warnings_list,
            requires_approval=True,
            model_calls=0,
            total_tokens=0,
            side_effect_free=True,
        )
        res.preview_digest = self._project_run_preview_digest(res)
        return res

    def _project_run_preview_digest(
        self,
        preview: ProjectRunPreviewResponse,
    ) -> str:
        tasks_data = [
            {
                "title": t.title,
                "assigned_agent": t.assigned_agent,
                "exact_files": list(t.exact_files),
                "verification": t.verification,
                "acceptance_criteria": list(t.acceptance_criteria),
            }
            for t in preview.tasks
        ]
        authoritative_payload = {
            "goal": preview.goal,
            "workspace_path": preview.workspace_path,
            "tasks": tasks_data,
            "exact_files": list(preview.exact_files),
            "verification_commands": list(preview.verification_commands),
            "requires_approval": preview.requires_approval,
            "side_effect_free": preview.side_effect_free,
        }
        canonical_json = json.dumps(
            authoritative_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return f"sha256:{digest_hex}"

    async def _active_command(self) -> SupervisorCommand | None:
        commands = await self.store.list()
        terminal_statuses = {"completed", "failed", "cancelled", "archived"}
        for cmd in commands:
            if getattr(cmd, "archived", False):
                continue
            if cmd.status not in terminal_statuses:
                return cmd
        return None

    async def commit_project_run(
        self,
        request: ProjectRunCommitRequest,
    ) -> ProjectRunCommitResponse:
        preview_req = ProjectRunPreviewRequest(
            goal=request.goal,
            workspace_path=request.workspace_path,
        )
        preview = await self.preview_project_run(preview_req)

        if request.preview_digest != preview.preview_digest:
            raise ValueError(
                "Stale veya değiştirilmiş preview digest: stale_project_run_preview"
            )

        commands = await self.store.list()
        for cmd in commands:
            if getattr(cmd, "archived", False):
                continue
            if (
                getattr(cmd, "project_run_preview_digest", None) == preview.preview_digest
                and getattr(cmd, "project_run_workspace_path", None) == preview.workspace_path
                and cmd.goal == preview.goal
            ):
                task_ids = [t.id for t in cmd.tasks]
                approval_ids = [t.approval_id for t in cmd.tasks if t.approval_id]
                return ProjectRunCommitResponse(
                    command_id=cmd.id,
                    status=cmd.status,
                    goal=cmd.goal,
                    workspace_path=preview.workspace_path,
                    preview_digest=preview.preview_digest,
                    task_ids=task_ids,
                    approval_ids=approval_ids,
                    requires_approval=True,
                    model_calls=0,
                    total_tokens=0,
                    execution_started=False,
                    created=False,
                )

        active = await self._active_command()
        if active is not None:
            raise ValueError("Zaten aktif bir görev/komut çalışıyor.")

        cmd_id = f"cmd_{secrets.token_hex(6)}"
        tasks: list[SupervisorTask] = []
        task_ids: list[str] = []
        approval_ids: list[str] = []

        for pt in preview.tasks:
            t_id = f"task_{secrets.token_hex(6)}"
            appr_id = f"appr_{secrets.token_hex(6)}"

            appr_preview_dict = {
                "task_title": pt.title,
                "exact_files": pt.exact_files,
                "verification": pt.verification,
                "workspace_path": preview.workspace_path,
            }

            task = SupervisorTask(
                id=t_id,
                title=pt.title,
                priority="zorunlu",
                assigned_agent=pt.assigned_agent,
                evidence=[{"type": "file", "value": f} for f in pt.exact_files],
                acceptance_criteria=pt.acceptance_criteria,
                dependencies=[],
                dependency_reason="Bağımsız görev adımı",
                parallelizable="evet",
                verification=pt.verification,
                user_approval="gerekli",
                exact_files=pt.exact_files,
                status="blocked",
                approval_id=appr_id,
                approval_state="pending",
                approval_description=f"Project Run adımı onay bekliyor: {pt.title}",
                approval_preview=appr_preview_dict,
            )
            tasks.append(task)
            task_ids.append(t_id)
            approval_ids.append(appr_id)

        command = SupervisorCommand(
            id=cmd_id,
            goal=preview.goal,
            status="awaiting_approval",
            autonomy_mode=request.autonomy_mode,
            plan_text=f"Project Run Plan: {len(preview.tasks)} adımlı deterministik plan",
            tasks=tasks,
            execution_layers=[task_ids],
            project_run_preview_digest=preview.preview_digest,
            project_run_workspace_path=preview.workspace_path,
        )

        self._event(
            command,
            type="project_run_committed",
            message=f"Project Run {len(tasks)} adımlı plan onay bekliyor.",
            data={
                "preview_digest": preview.preview_digest,
                "workspace_path": preview.workspace_path,
                "task_count": len(tasks),
                "requires_approval": True,
                "execution_started": False,
                "model_calls": 0,
                "total_tokens": 0,
            },
        )

        await self.store.put(command)

        return ProjectRunCommitResponse(
            command_id=cmd_id,
            status=command.status,
            goal=command.goal,
            workspace_path=preview.workspace_path,
            preview_digest=preview.preview_digest,
            task_ids=task_ids,
            approval_ids=approval_ids,
            requires_approval=True,
            model_calls=0,
            total_tokens=0,
            execution_started=False,
            created=True,
        )

    def _capture_snapshot_if_needed(
        self,
        command: SupervisorCommand,
        task: SupervisorTask,
    ) -> None:
        try:
            workspace_path = getattr(command, "project_run_workspace_path", ".") or "."
            self.snapshot_manager.capture_task_snapshot(
                command_id=command.id,
                task_id=task.id,
                workspace_path=workspace_path,
                exact_files=task.exact_files,
                workspace_root=self.settings.workspace_root,
                max_file_bytes=self.settings.workspace_max_file_bytes,
                max_search_results=self.settings.workspace_max_search_results,
            )
            self._event(
                command,
                type="run_snapshot_captured",
                task_id=task.id,
                message=f"{task.id} için pre-write snapshot alındı.",
                data={
                    "task_id": task.id,
                    "exact_files": task.exact_files,
                },
            )
        except Exception as exc:
            err_str = str(exc)
            if "Sensitive" in err_str or "limitini aşıyor" in err_str or "geçersiz" in err_str:
                raise ValueError(f"Snapshot alınamadı: {exc}") from exc

    async def get_command_change_review(
        self,
        command_id: str,
    ) -> RunChangeReviewResponse:
        command = await self.store.get(command_id)
        changed_files = self.snapshot_manager.build_command_change_review(
            command=command,
            workspace_root=self.settings.workspace_root,
            max_file_bytes=self.settings.workspace_max_file_bytes,
            max_search_results=self.settings.workspace_max_search_results,
        )

        changed_file_count = len(
            [f for f in changed_files if f.change_type != "unchanged"]
        )

        verification_summary = [
            {
                "task_id": t.id,
                "title": t.title,
                "verification": t.verification,
                "effective_verification": t.effective_verification,
                "status": t.status,
            }
            for t in command.tasks
        ]

        terminal_statuses = {"completed", "failed", "cancelled"}
        is_terminal = command.status in terminal_statuses

        can_revert = is_terminal and any(f.revertable for f in changed_files)

        model_calls = 0
        input_tokens = 0
        output_tokens = 0
        last_resp = getattr(command, "last_agent_response", None)
        if last_resp:
            model_calls = getattr(last_resp, "model_calls_used", 0)

        delivery_summary = getattr(command, "last_answer", None) or f"Komut durumu: {command.status}"

        return RunChangeReviewResponse(
            command_id=command.id,
            status=command.status,
            terminal=is_terminal,
            changed_files=changed_files,
            changed_file_count=changed_file_count,
            verification_summary=verification_summary,
            model_calls=model_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            delivery_summary=delivery_summary,
            can_revert=can_revert,
            revert_confirmation=f"REVERT {command.id}",
        )

    async def revert_command_changes(
        self,
        command_id: str,
        request: RunRevertRequest,
    ) -> RunRevertResponse:
        command = await self.store.get(command_id)
        result = self.snapshot_manager.revert_command_changes(
            command=command,
            workspace_root=self.settings.workspace_root,
            confirmation=request.confirmation,
            max_file_bytes=self.settings.workspace_max_file_bytes,
            max_search_results=self.settings.workspace_max_search_results,
        )

        self._event(
            command,
            type="run_changes_reverted",
            message=(
                f"Komut değişiklikleri geri alındı ({len(result.reverted)} dosya geri alındı, "
                f"{len(result.conflicts)} çakışma)."
            ),
            data={
                "reverted": result.reverted,
                "skipped": result.skipped,
                "conflicts": result.conflicts,
            },
        )
        await self.store.put(command)
        return result

    async def list_project_run_history(
        self,
        *,
        workspace_path: str,
        status_filter: str = "all",
        limit: int = 20,
        offset: int = 0,
    ) -> ProjectRunHistoryResponse:
        clean_path = workspace_path.strip() if workspace_path else "."
        if not clean_path:
            clean_path = "."

        try:
            policy = WorkspacePolicy(
                root=self.settings.workspace_root,
                max_file_bytes=self.settings.workspace_max_file_bytes,
                max_search_results=self.settings.workspace_max_search_results,
            )
            resolved = policy.resolve(clean_path, must_exist=False)
            policy.ensure_not_sensitive(resolved)
            try:
                norm_ws_path = resolved.relative_to(self.settings.workspace_root).as_posix()
            except ValueError:
                norm_ws_path = "."
            if norm_ws_path == "":
                norm_ws_path = "."
        except Exception as exc:
            raise ValueError(f"Geçersiz veya engellenmiş proje yolu '{workspace_path}': {exc}") from exc

        all_commands = await self.store.list()

        project_commands = [
            cmd for cmd in all_commands
            if getattr(cmd, "project_run_preview_digest", None) is not None
            and getattr(cmd, "project_run_workspace_path", None) is not None
        ]

        matching_commands = [
            cmd for cmd in project_commands
            if cmd.project_run_workspace_path == norm_ws_path or (
                norm_ws_path == "." and (cmd.project_run_workspace_path in (".", ""))
            )
        ]

        sf = status_filter.lower().strip()
        filtered_commands: list[SupervisorCommand] = []

        for cmd in matching_commands:
            cmd_status = cmd.status
            has_waiting_approval = any(
                t.status == "awaiting_approval" or getattr(t, "approval_state", "idle") == "pending"
                for t in cmd.tasks
            )

            if sf == "all":
                filtered_commands.append(cmd)
            elif sf == "active":
                if cmd_status in ("planning", "ready", "running", "reviewing", "awaiting_approval") and cmd_status not in ("completed", "failed", "cancelled"):
                    filtered_commands.append(cmd)
            elif sf == "waiting_approval":
                if cmd_status == "awaiting_approval" or has_waiting_approval:
                    filtered_commands.append(cmd)
            elif sf == "completed":
                if cmd_status == "completed":
                    filtered_commands.append(cmd)
            elif sf == "failed":
                if cmd_status == "failed":
                    filtered_commands.append(cmd)
            elif sf == "cancelled":
                if cmd_status == "cancelled":
                    filtered_commands.append(cmd)

        def sort_key(c: SupervisorCommand):
            created = c.created_at or ""
            return (created, c.id)

        filtered_commands.sort(key=sort_key, reverse=True)

        total = len(filtered_commands)

        limit_val = max(1, min(limit, 100))
        offset_val = max(0, offset)
        sliced_commands = filtered_commands[offset_val : offset_val + limit_val]

        items: list[ProjectRunHistoryItem] = []
        for cmd in sliced_commands:
            changed_file_count = 0
            try:
                chg = self.snapshot_manager.build_command_change_review(
                    command=cmd,
                    workspace_root=self.settings.workspace_root,
                    max_file_bytes=self.settings.workspace_max_file_bytes,
                    max_search_results=self.settings.workspace_max_search_results,
                )
                changed_file_count = len([f for f in chg if f.change_type != "unchanged"])
            except Exception:
                pass

            model_calls = 0
            input_tokens = 0
            output_tokens = 0
            last_resp = getattr(cmd, "last_agent_response", None)
            if last_resp:
                model_calls = getattr(last_resp, "model_calls_used", 0)
                input_tokens = getattr(last_resp, "input_tokens_used", 0)
                output_tokens = getattr(last_resp, "output_tokens_used", 0)

            last_event = cmd.events[-1].message if cmd.events else None

            task_summaries: list[ProjectRunHistoryTaskSummary] = []
            for t in cmd.tasks:
                retry_available = True
                retry_block_reason: str | None = None

                if cmd.status == "running":
                    retry_available = False
                    retry_block_reason = "Command execution is active"
                elif t.status == "running":
                    retry_available = False
                    retry_block_reason = "Task is currently running"
                elif t.status == "completed":
                    retry_available = False
                    retry_block_reason = "Task completed successfully"
                elif t.status not in ("failed", "rework_required", "blocked"):
                    if t.status == "awaiting_approval" or getattr(t, "approval_state", "idle") == "pending":
                        retry_available = True
                        retry_block_reason = None
                    else:
                        retry_available = False
                        retry_block_reason = f"Task status is '{t.status}'"

                task_summaries.append(
                    ProjectRunHistoryTaskSummary(
                        task_id=t.id,
                        title=t.title,
                        status=t.status,
                        approval_state=getattr(t, "approval_state", "idle"),
                        attempts=t.attempts,
                        exact_file_count=len(t.exact_files) if t.exact_files else 0,
                        verification=t.verification or "",
                        retry_available=retry_available,
                        retry_block_reason=retry_block_reason,
                    )
                )

            task_count = len(cmd.tasks)
            completed_count = len([t for t in cmd.tasks if t.status == "completed"])
            failed_count = len([t for t in cmd.tasks if t.status in ("failed", "rework_required")])
            waiting_count = len([t for t in cmd.tasks if t.status == "awaiting_approval" or getattr(t, "approval_state", "idle") == "pending"])
            progress = int((completed_count / task_count) * 100) if task_count > 0 else 0

            items.append(
                ProjectRunHistoryItem(
                    command_id=cmd.id,
                    goal=cmd.goal,
                    workspace_path=cmd.project_run_workspace_path or norm_ws_path,
                    status=cmd.status,
                    created_at=cmd.created_at,
                    updated_at=cmd.updated_at,
                    task_count=task_count,
                    completed_task_count=completed_count,
                    failed_task_count=failed_count,
                    waiting_approval_count=waiting_count,
                    progress_percent=progress,
                    changed_file_count=changed_file_count,
                    model_calls=model_calls,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    last_event=last_event,
                    tasks=task_summaries,
                )
            )

        return ProjectRunHistoryResponse(
            workspace_path=norm_ws_path,
            status_filter=sf,
            items=items,
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    async def request_project_run_task_retry(
        self,
        *,
        command_id: str,
        task_id: str,
        request: ProjectRunRetryRequest,
    ) -> ProjectRunRetryResponse:
        import uuid

        command = await self.store.get(command_id)
        if not command:
            raise KeyError(f"Command '{command_id}' bulunamadı.")

        if getattr(command, "project_run_preview_digest", None) is None:
            raise ValueError(f"Command '{command_id}' bir Project Run komutu değil.")

        task = next((t for t in command.tasks if t.id == task_id), None)
        if not task:
            raise KeyError(f"Task '{task_id}' command '{command_id}' içinde bulunamadı.")

        if command.status == "running":
            raise ValueError("Command üzerinde aktif execution çalışıyor, retry isteği oluşturulamaz.")

        if task.status == "running":
            raise ValueError(f"Task '{task_id}' şu anda çalışıyor, retry isteği oluşturulamaz.")

        if task.status == "completed":
            raise ValueError(f"Tamamlanmış task '{task_id}' retry edilemez.")

        if getattr(task, "approval_state", "idle") == "pending" and getattr(task, "approval_id", None):
            return ProjectRunRetryResponse(
                command_id=command.id,
                task_id=task.id,
                approval_id=task.approval_id,
                approval_version=task.approval_version,
                approval_state="pending",
                task_status=task.status,
                execution_started=False,
                model_calls=0,
                total_tokens=0,
            )

        reason_text = (request.reason or "").strip()[:1000]
        approval_id = f"appr_retry_{task.id}_{uuid.uuid4().hex[:8]}"
        new_version = (getattr(task, "approval_version", 0) or 0) + 1
        desc = f"Retry task '{task.title}'" + (f": {reason_text}" if reason_text else "")
        preview = {
            "exact_files": task.exact_files,
            "verification": task.verification,
            "attempts": task.attempts,
            "reason": reason_text if reason_text else None,
        }

        task.approval_id = approval_id
        task.approval_version = new_version
        task.approval_state = "pending"
        task.approval_description = desc
        task.approval_preview = preview
        task.status = "awaiting_approval"

        if command.status not in ("completed", "failed"):
            command.status = "awaiting_approval"

        self._event(
            command,
            type="project_run_retry_requested",
            message=f"Retry approval requested for task '{task.title}'",
            task_id=task.id,
            data={
                "task_id": task.id,
                "approval_id": approval_id,
                "attempts": task.attempts,
                "execution_started": False,
                "model_calls": 0,
                "total_tokens": 0,
            },
        )

        await self.store.put(command)

        return ProjectRunRetryResponse(
            command_id=command.id,
            task_id=task.id,
            approval_id=approval_id,
            approval_version=new_version,
            approval_state="pending",
            task_status=task.status,
            model_calls=0,
            total_tokens=0,
        )

    async def list_mission_events(
        self,
        command_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> MissionEventPage:
        command = await self.get(command_id)
        journal = self._get_event_journal()

        if journal.has_journal(mission_id=command_id):
            raw_events = journal.list_events(
                mission_id=command_id,
                after_sequence=after_sequence,
                limit=limit + 1,
            )
            has_more = len(raw_events) > limit
            events = raw_events[:limit]
            next_after = events[-1].sequence if (has_more and events) else None
            last_seq = events[-1].sequence if events else 0
            last_hash = events[-1].event_hash if events else None

            return MissionEventPage(
                mission_id=command_id,
                events=events,
                count=len(events),
                after_sequence=after_sequence,
                next_after_sequence=next_after,
                has_more=has_more,
                source="journal",
                integrity_verified=True,
                last_sequence=last_seq,
                last_event_hash=last_hash,
            )

        if not command.events:
            return MissionEventPage(
                mission_id=command_id,
                events=[],
                count=0,
                after_sequence=after_sequence,
                next_after_sequence=None,
                has_more=False,
                source="empty",
                integrity_verified=True,
                last_sequence=0,
                last_event_hash=None,
            )

        mapped_records: list[MissionEventRecord] = []
        prev_hash: str | None = None

        for idx, ev in enumerate(command.events, start=1):
            dt = datetime.now(timezone.utc)
            if isinstance(ev.created_at, str):
                try:
                    dt = datetime.fromisoformat(ev.created_at)
                except Exception:
                    pass
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            ev_id = f"legacy-{idx}-{hashlib.sha256((ev.type + str(ev.created_at)).encode('utf-8')).hexdigest()[:12]}"
            kind = canonical_event_kind(ev.type)
            payload = {"message": ev.message, **(ev.data or {})}
            san_payload = sanitize_payload(payload)

            dt_iso = dt.astimezone(timezone.utc).isoformat()
            ev_hash = compute_canonical_event_hash(
                schema_version=1,
                event_id=ev_id,
                mission_id=command_id,
                sequence=idx,
                event_type=ev.type,
                canonical_kind=kind,
                occurred_at_iso=dt_iso,
                task_id=ev.task_id,
                approval_id=ev.data.get("approval_id") if isinstance(ev.data, dict) else None,
                actor="supervisor",
                payload=san_payload,
                previous_hash=prev_hash,
            )

            record = MissionEventRecord(
                schema_version=1,
                event_id=ev_id,
                mission_id=command_id,
                sequence=idx,
                event_type=ev.type,
                canonical_kind=kind,
                occurred_at=dt,
                task_id=ev.task_id,
                approval_id=ev.data.get("approval_id") if isinstance(ev.data, dict) else None,
                actor="supervisor",
                payload=san_payload,
                previous_hash=prev_hash,
                event_hash=ev_hash,
            )
            mapped_records.append(record)
            prev_hash = ev_hash

        filtered = [rec for rec in mapped_records if rec.sequence > after_sequence]
        has_more = len(filtered) > limit
        events = filtered[:limit]
        next_after = events[-1].sequence if (has_more and events) else None
        last_seq = mapped_records[-1].sequence if mapped_records else 0
        last_hash = mapped_records[-1].event_hash if mapped_records else None

        return MissionEventPage(
            mission_id=command_id,
            events=events,
            count=len(events),
            after_sequence=after_sequence,
            next_after_sequence=next_after,
            has_more=has_more,
            source="legacy_command_events",
            integrity_verified=False,
            last_sequence=last_seq,
            last_event_hash=last_hash,
        )

    async def get_mission_state_projection(
        self,
        command_id: str,
    ) -> MissionStateProjection:
        command = await self.get(command_id)
        journal = self._get_event_journal()

        if journal.has_journal(mission_id=command_id):
            return journal.project_state(mission_id=command_id)

        page = await self.list_mission_events(command_id=command_id, after_sequence=0, limit=100000)
        events = page.events

        if not events:
            return MissionStateProjection(
                mission_id=command_id,
                event_count=0,
                last_sequence=0,
                last_event_type=None,
                command_status=command.status,
                task_statuses={},
                pending_approval_ids=[],
                terminal=(command.status in {"completed", "failed", "cancelled", "reverted"}),
            )

        cmd_status: str | None = None
        task_stats: dict[str, str] = {}
        pending_apps: list[str] = []

        for ev in events:
            p = ev.payload or {}
            c_stat = p.get("command_status")
            if isinstance(c_stat, str) and c_stat:
                cmd_status = c_stat

            t_id = ev.task_id
            t_stat = p.get("task_status")
            if t_id and isinstance(t_stat, str) and t_stat:
                task_stats[t_id] = t_stat

            p_apps = p.get("pending_approval_ids")
            if isinstance(p_apps, list):
                clean_p_apps = [str(x) for x in p_apps if isinstance(x, str) and x]
                seen = set()
                uniq_p_apps = []
                for item in clean_p_apps:
                    if item not in seen:
                        seen.add(item)
                        uniq_p_apps.append(item)
                pending_apps = uniq_p_apps

        if cmd_status is None:
            cmd_status = command.status

        terminal = cmd_status in {"completed", "failed", "cancelled", "reverted"}

        return MissionStateProjection(
            mission_id=command_id,
            event_count=len(events),
            last_sequence=events[-1].sequence,
            last_event_type=events[-1].event_type,
            command_status=cmd_status,
            task_statuses=task_stats,
            pending_approval_ids=pending_apps,
            terminal=terminal,
        )

    async def list_execution_receipts(
        self,
        command_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> ExecutionReceiptPage:
        command = await self.get(command_id)
        receipt_store = self._get_execution_receipt_store()

        if receipt_store.has_receipts(mission_id=command_id):
            raw_receipts = receipt_store.list_receipts(
                mission_id=command_id,
                after_sequence=after_sequence,
                limit=limit + 1,
            )
            has_more = len(raw_receipts) > limit
            receipts = raw_receipts[:limit]
            next_after = receipts[-1].sequence if (has_more and receipts) else None
            last_seq = receipts[-1].sequence if receipts else 0
            last_hash = receipts[-1].receipt_hash if receipts else None

            return ExecutionReceiptPage(
                mission_id=command_id,
                receipts=receipts,
                count=len(receipts),
                after_sequence=after_sequence,
                next_after_sequence=next_after,
                has_more=has_more,
                source="receipt_store",
                integrity_verified=True,
                last_sequence=last_seq,
                last_receipt_hash=last_hash,
            )

        return ExecutionReceiptPage(
            mission_id=command_id,
            receipts=[],
            count=0,
            after_sequence=after_sequence,
            next_after_sequence=None,
            has_more=False,
            source="empty",
            integrity_verified=True,
            last_sequence=0,
            last_receipt_hash=None,
        )

    async def get_execution_receipt(
        self,
        command_id: str,
        receipt_id: str,
    ) -> ExecutionReceipt:
        command = await self.get(command_id)
        receipt_store = self._get_execution_receipt_store()
        receipt = receipt_store.get_receipt(mission_id=command_id, receipt_id=receipt_id)
        if receipt is None:
            raise KeyError(f"Execution receipt '{receipt_id}' command '{command_id}' için bulunamadı.")
        return receipt

    async def list_mission_checkpoints(
        self,
        command_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> MissionCheckpointPage:
        command = await self.get(command_id)
        checkpoint_store = self._get_mission_checkpoint_store()

        if checkpoint_store.has_checkpoints(mission_id=command_id):
            raw_recs = checkpoint_store.list_checkpoints(
                mission_id=command_id,
                after_sequence=after_sequence,
                limit=limit + 1,
            )
            has_more = len(raw_recs) > limit
            recs = raw_recs[:limit]

            next_after = recs[-1].sequence if (has_more and recs) else None
            last_seq = recs[-1].sequence if recs else 0
            last_hash = recs[-1].checkpoint_hash if recs else None

            return MissionCheckpointPage(
                mission_id=command_id,
                checkpoints=recs,
                count=len(recs),
                after_sequence=after_sequence,
                next_after_sequence=next_after,
                has_more=has_more,
                source="checkpoint_store",
                integrity_verified=True,
                last_sequence=last_seq,
                last_checkpoint_hash=last_hash,
            )

        return MissionCheckpointPage(
            mission_id=command_id,
            checkpoints=[],
            count=0,
            after_sequence=after_sequence,
            next_after_sequence=None,
            has_more=False,
            source="empty",
            integrity_verified=True,
            last_sequence=0,
            last_checkpoint_hash=None,
        )

    async def get_mission_checkpoint(
        self,
        command_id: str,
        checkpoint_id: str,
    ) -> MissionCheckpointRecord:
        command = await self.get(command_id)
        checkpoint_store = self._get_mission_checkpoint_store()
        rec = checkpoint_store.get_checkpoint(
            mission_id=command_id,
            checkpoint_id=checkpoint_id,
        )
        if rec is None:
            raise KeyError(f"Mission checkpoint '{checkpoint_id}' command '{command_id}' için bulunamadı.")
        return rec

    async def get_mission_history(
        self,
        command_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> MissionHistoryPage:
        command = await self.get(command_id)
        event_page = await self.list_mission_events(
            command_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        receipt_ids: set[str] = set()
        checkpoint_ids: set[str] = set()
        for event in event_page.events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            for key in ("receipt_id", "source_receipt_id"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    receipt_ids.add(value.strip())
            for key in ("checkpoint_id", "recovery_checkpoint_id"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    checkpoint_ids.add(value.strip())
        try:
            receipts = {
                receipt_id: await self.get_execution_receipt(command_id, receipt_id)
                for receipt_id in sorted(receipt_ids)
            }
            checkpoints = {
                checkpoint_id: await self.get_mission_checkpoint(command_id, checkpoint_id)
                for checkpoint_id in sorted(checkpoint_ids)
            }
        except KeyError as exc:
            raise MissionHistoryIntegrityError(
                "Referenced immutable Mission evidence is missing."
            ) from exc
        return build_mission_history_page(
            command=command,
            event_page=event_page,
            receipts_by_id=receipts,
            checkpoints_by_id=checkpoints,
        )

    async def _load_complete_mission_evidence(
        self,
        command_id: str,
    ) -> tuple[MissionEventPage, list[ExecutionReceipt], list[MissionCheckpointRecord]]:
        event_page = await self.list_mission_events(
            command_id,
            after_sequence=0,
            limit=MAX_MISSION_HISTORY_RECORDS + 1,
        )
        if event_page.has_more or len(event_page.events) > MAX_MISSION_HISTORY_RECORDS:
            raise MissionHistoryLimitError("Mission event limit exceeded.")
        receipt_page = await self.list_execution_receipts(
            command_id,
            after_sequence=0,
            limit=MAX_MISSION_HISTORY_RECORDS + 1,
        )
        if receipt_page.has_more or len(receipt_page.receipts) > MAX_MISSION_HISTORY_RECORDS:
            raise MissionHistoryLimitError("Mission receipt limit exceeded.")
        checkpoint_page = await self.list_mission_checkpoints(
            command_id,
            after_sequence=0,
            limit=MAX_MISSION_HISTORY_RECORDS + 1,
        )
        if checkpoint_page.has_more or len(checkpoint_page.checkpoints) > MAX_MISSION_HISTORY_RECORDS:
            raise MissionHistoryLimitError("Mission checkpoint limit exceeded.")
        return event_page, receipt_page.receipts, checkpoint_page.checkpoints

    async def get_mission_post_run_summary(
        self,
        command_id: str,
    ) -> MissionPostRunSummary:
        command = await self.get(command_id)
        if command.status not in {"completed", "failed"}:
            raise ValueError(
                "Post-run summary is available only for completed or failed Missions."
            )
        event_page, receipts, checkpoints = await self._load_complete_mission_evidence(command_id)
        return build_mission_post_run_summary(
            command=command,
            event_page=event_page,
            receipts=receipts,
            checkpoints=checkpoints,
        )
