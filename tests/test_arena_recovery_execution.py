from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.arena.execution import (
    ArenaRecoveryApprovalError,
    ArenaRecoveryConflictError,
    ArenaRecoveryExecutor,
    ArenaRecoveryQuotaError,
    ArenaRecoveryUnavailableError,
)
from app.core.config import Settings
from app.main import app


class _Quota:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.reason = (
            "Ücretsiz kota koruma payından sonra Arena için yeterli."
            if allowed
            else "Ücretsiz Arena kotası yetersiz."
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "minimum_calls": 1,
            "usable_calls": 10 if self.allowed else 0,
            "routes": [],
        }


class _ControlledRunner:
    def __init__(
        self,
        *,
        started: asyncio.Event,
        release: asyncio.Event,
        calls: dict[str, int],
        quota_allowed: bool,
        progress,
        **kwargs,
    ) -> None:
        self.started = started
        self.release = release
        self.calls = calls
        self.quota_allowed = quota_allowed
        self.progress = progress
        self.kwargs = kwargs

    async def quota_plan(self, scenario):
        self.calls["quota"] += 1
        return _Quota(allowed=self.quota_allowed)

    async def run(self, scenario):
        self.calls["run"] += 1
        self.started.set()
        self.progress("fake_started", {"scenario": scenario.id})
        await self.release.wait()
        self.progress("fake_finished", {"status": "completed"})
        return SimpleNamespace(
            status="completed",
            run_id="new-product-run",
            workspace="workspace/new-product-run",
            failure_reason=None,
        )


def _source_and_plan() -> tuple[dict, dict]:
    source = {
        "run_id": "source-run",
        "scenario_id": "existing_vanilla_repair",
        "status": "failed",
    }
    plan = {
        "run_id": "source-run",
        "scenario_id": "existing_vanilla_repair",
        "execution_available": True,
        "approval_phrase": (
            "ARENA RERUN existing_vanilla_repair FROM source-run"
        ),
    }
    return source, plan


@pytest.mark.asyncio
async def test_executor_runs_one_fresh_approved_rerun_and_preserves_source(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"quota": 0, "run": 0}
    runners: list[_ControlledRunner] = []

    def factory(**kwargs):
        runner = _ControlledRunner(
            started=started,
            release=release,
            calls=calls,
            quota_allowed=True,
            **kwargs,
        )
        runners.append(runner)
        return runner

    executor = ArenaRecoveryExecutor(
        project_root=tmp_path,
        workspace_root=tmp_path / "workspace" / "arena-recovery",
        history_directory=tmp_path / "data",
        runner_factory=factory,
    )
    source, plan = _source_and_plan()
    source_before = deepcopy(source)

    created = await executor.start(
        source_run=source,
        recovery_plan=plan,
        approval_phrase=plan["approval_phrase"],
    )
    assert created["status"] == "queued"
    assert created["source_run_id"] == "source-run"
    assert created["scenario_id"] == "existing_vanilla_repair"
    assert Path(created["workspace_root"]).name.startswith(
        "arena-recovery-"
    )
    assert Path(created["history_path"]).name.startswith(
        "arena-recovery-"
    )
    assert Path(created["history_path"]).suffix == ".db"
    assert Path(created["log_path"]).suffix == ".log"
    assert source == source_before

    await asyncio.wait_for(started.wait(), timeout=1.0)
    with pytest.raises(ArenaRecoveryConflictError):
        await executor.start(
            source_run=source,
            recovery_plan=plan,
            approval_phrase=plan["approval_phrase"],
        )

    release.set()
    for _ in range(100):
        current = executor.get(created["execution_id"])
        assert current is not None
        if current["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("Recovery yürütmesi tamamlanmadı.")

    assert current["product_status"] == "completed"
    assert current["result_run_id"] == "new-product-run"
    assert current["result_workspace"] == "workspace/new-product-run"
    assert current["failure_reason"] is None
    assert calls == {"quota": 1, "run": 1}
    assert len(runners) == 1
    log_text = Path(current["log_path"]).read_text(encoding="utf-8")
    assert "fake_started" in log_text
    assert "fake_finished" in log_text
    with pytest.raises(ArenaRecoveryConflictError):
        await executor.start(
            source_run=source,
            recovery_plan=plan,
            approval_phrase=plan["approval_phrase"],
        )
    assert calls == {"quota": 1, "run": 1}
    await executor.close()


@pytest.mark.asyncio
async def test_executor_rejects_wrong_approval_and_mismatched_plan(
    tmp_path: Path,
) -> None:
    constructed = 0

    def factory(**kwargs):
        nonlocal constructed
        constructed += 1
        raise AssertionError("Runner oluşturulmamalı.")

    executor = ArenaRecoveryExecutor(
        project_root=tmp_path,
        workspace_root=tmp_path / "workspace",
        history_directory=tmp_path / "data",
        runner_factory=factory,
    )
    source, plan = _source_and_plan()

    with pytest.raises(ArenaRecoveryApprovalError):
        await executor.start(
            source_run=source,
            recovery_plan=plan,
            approval_phrase="yanlış onay",
        )

    mismatched = dict(plan, run_id="other-run")
    with pytest.raises(ArenaRecoveryUnavailableError):
        await executor.start(
            source_run=source,
            recovery_plan=mismatched,
            approval_phrase=mismatched["approval_phrase"],
        )

    blocked = dict(plan, execution_available=False, approval_phrase=None)
    with pytest.raises(ArenaRecoveryUnavailableError):
        await executor.start(
            source_run=source,
            recovery_plan=blocked,
            approval_phrase="anything",
        )
    assert constructed == 0


@pytest.mark.asyncio
async def test_executor_fails_before_live_run_when_quota_is_not_allowed(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"quota": 0, "run": 0}

    def factory(**kwargs):
        return _ControlledRunner(
            started=started,
            release=release,
            calls=calls,
            quota_allowed=False,
            **kwargs,
        )

    executor = ArenaRecoveryExecutor(
        project_root=tmp_path,
        workspace_root=tmp_path / "workspace",
        history_directory=tmp_path / "data",
        runner_factory=factory,
    )
    source, plan = _source_and_plan()

    with pytest.raises(ArenaRecoveryQuotaError):
        await executor.start(
            source_run=source,
            recovery_plan=plan,
            approval_phrase=plan["approval_phrase"],
        )
    assert calls == {"quota": 1, "run": 0}
    assert not started.is_set()
    await executor.close()


def _write_failed_run(path: Path) -> None:
    result = {
        "run_id": "http-source-run",
        "scenario_id": "existing_vanilla_repair",
        "scenario_title": "Existing Vanilla Repair",
        "mission_id": "mission-1",
        "status": "failed",
        "failure_reason": "Eksik artifact.",
        "elapsed_seconds": 1.0,
        "workspace": "workspace/source",
        "approvals_applied": 0,
        "decisions_answered": 0,
        "required_paths_ok": False,
        "missing_required_paths": ["src/calculator.js"],
        "protected_paths_ok": True,
        "changed_protected_paths": [],
        "baseline_verifications": [],
        "verifications": [],
        "usage": {
            "model_calls": 1,
            "successful_calls": 1,
            "failed_calls": 0,
            "total_tokens": 100,
        },
        "mission_usage": None,
        "task_attempts": 1,
        "failure_records": 0,
        "score": {"total": 10.0},
        "coordination": {},
        "context_compiler": {},
        "handoffs": [],
        "tasks": [{"id": "TASK-001", "status": "blocked"}],
        "last_events": [],
    }
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE arena_runs (
                run_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL,
                mission_id TEXT, status TEXT NOT NULL, score REAL NOT NULL,
                elapsed_seconds REAL NOT NULL, model_calls INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL, approvals INTEGER NOT NULL,
                decisions INTEGER NOT NULL, result_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO arena_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result["run_id"],
                result["scenario_id"],
                result["mission_id"],
                result["status"],
                result["score"]["total"],
                result["elapsed_seconds"],
                1,
                100,
                0,
                0,
                json.dumps(result),
                1.0,
            ),
        )
        connection.commit()


class _HttpExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.execution = {
            "execution_id": "execution-1",
            "source_run_id": "http-source-run",
            "scenario_id": "existing_vanilla_repair",
            "status": "queued",
            "history_path": "data/arena-recovery-execution-1.db",
            "log_path": "data/arena-recovery-execution-1.log",
            "workspace_root": "workspace/arena-recovery/execution-1",
        }

    async def start(self, *, source_run, recovery_plan, approval_phrase):
        expected = recovery_plan["approval_phrase"]
        if approval_phrase != expected:
            raise ArenaRecoveryApprovalError("Onay eşleşmedi.")
        self.calls.append(
            {
                "source_run": source_run,
                "recovery_plan": recovery_plan,
                "approval_phrase": approval_phrase,
            }
        )
        return dict(self.execution)

    def get(self, execution_id: str):
        if execution_id == self.execution["execution_id"]:
            return dict(self.execution)
        return None


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_http_recovery_execution_requires_csrf_and_exact_approval(
    tmp_path: Path,
) -> None:
    database = tmp_path / "arena-live-http-recovery.db"
    _write_failed_run(database)
    before = database.read_bytes()
    stub = _HttpExecutor()

    previous_settings = getattr(app.state, "settings", None)
    previous_executor = getattr(
        app.state,
        "arena_recovery_executor",
        None,
    )
    app.state.settings = Settings(
        _env_file=None,
        workspace_root=tmp_path / "workspace",
        arena_history_directory=tmp_path,
        arena_history_max_databases=20,
    )
    app.state.arena_recovery_executor = stub
    try:
        client = TestClient(app)
        phrase = (
            "ARENA RERUN existing_vanilla_repair FROM http-source-run"
        )
        no_csrf = client.post(
            "/v1/arena/runs/http-source-run/recovery-executions",
            json={"approval_phrase": phrase},
        )
        assert no_csrf.status_code == 403
        assert stub.calls == []

        wrong = client.post(
            "/v1/arena/runs/http-source-run/recovery-executions",
            headers={"X-Prometheus-CSRF": "1"},
            json={"approval_phrase": "wrong"},
        )
        assert wrong.status_code == 403
        assert stub.calls == []

        started = client.post(
            "/v1/arena/runs/http-source-run/recovery-executions",
            headers={"X-Prometheus-CSRF": "1"},
            json={"approval_phrase": phrase},
        )
        assert started.status_code == 202
        assert started.json()["execution_id"] == "execution-1"
        assert len(stub.calls) == 1

        status = client.get(
            "/v1/arena/recovery-executions/execution-1"
        )
        assert status.status_code == 200
        assert status.json()["status"] == "queued"

        missing = client.get(
            "/v1/arena/recovery-executions/missing"
        )
        assert missing.status_code == 404
        assert database.read_bytes() == before
    finally:
        if previous_settings is None:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
        if previous_executor is None:
            delattr(app.state, "arena_recovery_executor")
        else:
            app.state.arena_recovery_executor = previous_executor
