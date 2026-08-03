from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hmac
import json
from pathlib import Path
import secrets
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.arena.catalog import get_scenario
from app.arena.runner import ArenaRunner


class ArenaRecoveryExecutionRequest(BaseModel):
    approval_phrase: str = Field(min_length=1, max_length=256)


class ArenaRecoveryExecutionError(RuntimeError):
    pass


class ArenaRecoveryApprovalError(ArenaRecoveryExecutionError):
    pass


class ArenaRecoveryUnavailableError(ArenaRecoveryExecutionError):
    pass


class ArenaRecoveryConflictError(ArenaRecoveryExecutionError):
    pass


class ArenaRecoveryQuotaError(ArenaRecoveryExecutionError):
    pass


RunnerFactory = Callable[..., ArenaRunner]


class ArenaRecoveryExecutor:
    """Approval-gated, single-flight execution of one fresh Arena rerun."""

    def __init__(
        self,
        *,
        project_root: Path,
        workspace_root: Path,
        history_directory: Path,
        runner_factory: RunnerFactory = ArenaRunner,
    ) -> None:
        self.project_root = project_root.resolve()
        self.workspace_root = workspace_root.resolve()
        self.history_directory = history_directory.resolve()
        self.runner_factory = runner_factory
        self._lock = asyncio.Lock()
        self._active_execution_id: str | None = None
        self._executions: dict[str, dict[str, Any]] = {}
        self._jobs: dict[str, asyncio.Task[None]] = {}

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _execution_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"arena-recovery-{timestamp}-{secrets.token_hex(3)}"

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.items()
            if key not in {"runner", "scenario"}
        }

    def get(self, execution_id: str) -> dict[str, Any] | None:
        record = self._executions.get(execution_id.strip())
        return self._public(record) if record else None

    def _progress_callback(
        self,
        execution_id: str,
        log_path: Path,
    ) -> Callable[[str, dict[str, Any]], None]:
        def emit(event: str, data: dict[str, Any]) -> None:
            payload = {
                "created_at": self._utc_now(),
                "event": event,
                "data": data,
            }
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            record = self._executions.get(execution_id)
            if record is not None:
                record["last_event"] = payload
                record["updated_at"] = payload["created_at"]

        return emit

    async def start(
        self,
        *,
        source_run: dict[str, Any],
        recovery_plan: dict[str, Any],
        approval_phrase: str,
    ) -> dict[str, Any]:
        expected = str(recovery_plan.get("approval_phrase") or "")
        if not recovery_plan.get("execution_available") or not expected:
            raise ArenaRecoveryUnavailableError(
                "Bu Arena koşusu için yürütülebilir recovery planı yok."
            )
        if not hmac.compare_digest(
            approval_phrase.strip().encode("utf-8"),
            expected.encode("utf-8"),
        ):
            raise ArenaRecoveryApprovalError(
                "Arena recovery onay cümlesi tam olarak eşleşmedi."
            )

        source_run_id = str(source_run.get("run_id") or "").strip()
        plan_run_id = str(recovery_plan.get("run_id") or "").strip()
        scenario_id = str(recovery_plan.get("scenario_id") or "").strip()
        source_scenario_id = str(source_run.get("scenario_id") or "").strip()
        if (
            not source_run_id
            or source_run_id != plan_run_id
            or scenario_id != source_scenario_id
        ):
            raise ArenaRecoveryUnavailableError(
                "Recovery planı kaynak Arena koşusuyla eşleşmiyor."
            )
        try:
            scenario = get_scenario(scenario_id)
        except KeyError as exc:
            raise ArenaRecoveryUnavailableError(str(exc)) from exc

        async with self._lock:
            if any(
                record.get("source_run_id") == source_run_id
                for record in self._executions.values()
            ):
                raise ArenaRecoveryConflictError(
                    "Bu kaynak Arena koşusu için recovery zaten başlatıldı."
                )
            if self._active_execution_id is not None:
                active = self._executions.get(self._active_execution_id)
                if active and active.get("status") in {"queued", "running"}:
                    raise ArenaRecoveryConflictError(
                        "Başka bir Arena recovery koşusu halen aktif."
                    )
                self._active_execution_id = None

            execution_id = self._execution_id()
            execution_workspace = self.workspace_root / execution_id
            history_path = self.history_directory / f"{execution_id}.db"
            log_path = self.history_directory / f"{execution_id}.log"
            for path in (execution_workspace, history_path, log_path):
                if path.exists():
                    raise ArenaRecoveryConflictError(
                        f"Recovery çıktı yolu zaten var: {path}"
                    )

            runner = self.runner_factory(
                project_root=self.project_root,
                workspace_root=execution_workspace,
                history_path=history_path,
                progress=self._progress_callback(execution_id, log_path),
            )
            quota = await runner.quota_plan(scenario)
            if not quota.allowed:
                raise ArenaRecoveryQuotaError(quota.reason)

            now = self._utc_now()
            record: dict[str, Any] = {
                "execution_id": execution_id,
                "source_run_id": source_run_id,
                "scenario_id": scenario.id,
                "status": "queued",
                "product_status": None,
                "result_run_id": None,
                "result_workspace": None,
                "failure_reason": None,
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
                "workspace_root": str(execution_workspace),
                "history_path": str(history_path),
                "log_path": str(log_path),
                "quota": quota.to_dict(),
                "last_event": None,
                "runner": runner,
                "scenario": scenario,
            }
            self._executions[execution_id] = record
            self._active_execution_id = execution_id
            job = asyncio.create_task(
                self._run(execution_id),
                name=f"arena-recovery:{execution_id}",
            )
            self._jobs[execution_id] = job
            return self._public(record)


    async def close(self) -> None:
        jobs = [job for job in self._jobs.values() if not job.done()]
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        self._jobs.clear()
        self._active_execution_id = None

    async def _run(self, execution_id: str) -> None:
        record = self._executions[execution_id]
        runner = record["runner"]
        scenario = record["scenario"]
        record["status"] = "running"
        record["started_at"] = self._utc_now()
        record["updated_at"] = record["started_at"]
        try:
            result = await runner.run(scenario)
            record["status"] = "completed"
            record["product_status"] = result.status
            record["result_run_id"] = result.run_id
            record["result_workspace"] = str(result.workspace)
            record["failure_reason"] = result.failure_reason
        except asyncio.CancelledError:
            record["status"] = "cancelled"
            record["failure_reason"] = "Arena recovery yürütmesi kapatıldı."
            raise
        except Exception as exc:  # noqa: BLE001 - status endpoint must retain failure
            record["status"] = "failed"
            record["failure_reason"] = str(exc)
        finally:
            record["finished_at"] = self._utc_now()
            record["updated_at"] = record["finished_at"]
            async with self._lock:
                if self._active_execution_id == execution_id:
                    self._active_execution_id = None
            self._jobs.pop(execution_id, None)
