from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.arena.diagnostics import diagnose_arena_run
from app.arena.recovery import build_arena_recovery_plan
from app.core.config import Settings
from app.main import app


def _result(
    *,
    run_id: str,
    scenario_id: str = "existing_vanilla_repair",
    status: str = "failed",
    failure_reason: str | None = "Koşu tamamlanamadı.",
    missing_paths: list[str] | None = None,
    changed_protected: list[str] | None = None,
    task_statuses: tuple[str, ...] = ("completed", "blocked"),
    retry_recovered: bool = False,
) -> dict:
    missing_paths = list(missing_paths or [])
    changed_protected = list(changed_protected or [])
    events = []
    failures = []
    failed_calls = 0
    if retry_recovered:
        events.append(
            {
                "type": "focused_provider_retry_scheduled",
                "message": "retry",
            }
        )
        failures.append(
            {
                "kind": "focused_provider_timeout",
                "summary": "timeout",
                "count": 1,
            }
        )
        failed_calls = 1
    tasks = []
    for index, task_status in enumerate(task_statuses, start=1):
        tasks.append(
            {
                "id": f"TASK-{index:03d}",
                "status": task_status,
                "failure_history": failures if index == len(task_statuses) else [],
            }
        )
    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_title": "Existing Vanilla Repair",
        "mission_id": "mission-1",
        "status": status,
        "failure_reason": failure_reason,
        "elapsed_seconds": 12.5,
        "workspace": "workspace/example",
        "approvals_applied": 0,
        "decisions_answered": 0,
        "required_paths_ok": not missing_paths,
        "missing_required_paths": missing_paths,
        "protected_paths_ok": not changed_protected,
        "changed_protected_paths": changed_protected,
        "baseline_verifications": [],
        "verifications": [
            {
                "name": "npm test",
                "success": status == "completed",
                "exit_code": 0 if status == "completed" else 1,
            }
        ],
        "usage": {
            "model_calls": 3,
            "successful_calls": 3 - failed_calls,
            "failed_calls": failed_calls,
            "total_tokens": 1200,
        },
        "mission_usage": None,
        "task_attempts": len(tasks),
        "failure_records": len(failures),
        "score": {"total": 99.5 if status == "completed" else 25.0},
        "coordination": {},
        "context_compiler": {},
        "handoffs": [],
        "tasks": tasks,
        "last_events": events,
    }


def _write_run(path: Path, result: dict) -> None:
    usage = result["usage"]
    score = result["score"]
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
                score["total"],
                result["elapsed_seconds"],
                usage["model_calls"],
                usage["total_tokens"],
                0,
                0,
                json.dumps(result),
                1.0,
            ),
        )
        connection.commit()


def test_failed_known_scenario_builds_approval_gated_fresh_rerun() -> None:
    result = _result(
        run_id="failed-run",
        missing_paths=["test/edge-cases.test.js"],
    )
    diagnosis = diagnose_arena_run(result)
    plan = build_arena_recovery_plan(
        result,
        diagnosis,
        known_scenarios={"existing_vanilla_repair"},
    )

    assert plan["decision"] == "ready_for_approval"
    assert plan["strategy"] == "fresh_scenario_rerun"
    assert plan["execution_available"] is True
    assert plan["requires_user_approval"] is True
    assert plan["approval_phrase"] == (
        "ARENA RERUN existing_vanilla_repair FROM failed-run"
    )
    assert plan["command_preview"] == (
        "python scripts/run_prometheus_arena.py "
        "--scenario existing_vanilla_repair --live"
    )
    assert plan["safeguards"]["preserve_source_run"] is True
    assert plan["safeguards"]["fresh_workspace_required"] is True
    assert plan["safeguards"]["one_live_invocation_only"] is True
    assert plan["safeguards"]["automatic_execution"] is False
    assert [step["code"] for step in plan["steps"]] == [
        "preserve_evidence",
        "quota_preflight",
        "fresh_output_paths",
        "explicit_approval",
        "single_live_run",
        "compare_result",
    ]


def test_scope_violation_blocks_rerun_until_manual_review() -> None:
    result = _result(
        run_id="scope-run",
        changed_protected=["test/contract.test.js"],
    )
    plan = build_arena_recovery_plan(
        result,
        known_scenarios={"existing_vanilla_repair"},
    )

    assert plan["decision"] == "blocked"
    assert plan["strategy"] == "manual_scope_review"
    assert plan["execution_available"] is False
    assert plan["rerun_recommended"] is False
    assert plan["approval_phrase"] is None
    assert plan["command_preview"] is None
    assert plan["source_diagnosis"]["primary_code"] == "scope_violation"


def test_healthy_delivery_does_not_recommend_another_live_run() -> None:
    result = _result(
        run_id="healthy-run",
        status="completed",
        failure_reason=None,
        task_statuses=("completed",),
    )
    plan = build_arena_recovery_plan(
        result,
        known_scenarios={"existing_vanilla_repair"},
    )

    assert plan["decision"] == "not_required"
    assert plan["strategy"] == "no_action"
    assert plan["rerun_recommended"] is False
    assert plan["execution_available"] is False
    assert plan["steps"][0]["code"] == "compare_history"


def test_recovered_provider_warning_is_optional_not_executable() -> None:
    result = _result(
        run_id="recovered-run",
        status="completed",
        failure_reason=None,
        task_statuses=("completed",),
        retry_recovered=True,
    )
    plan = build_arena_recovery_plan(
        result,
        known_scenarios={"existing_vanilla_repair"},
    )

    assert plan["decision"] == "optional"
    assert plan["strategy"] == "compare_before_rerun"
    assert plan["execution_available"] is False
    assert plan["source_diagnosis"]["primary_code"] == (
        "provider_retry_recovered"
    )


def test_unknown_scenario_cannot_generate_executable_command() -> None:
    result = _result(
        run_id="unknown-run",
        scenario_id="retired_scenario",
    )
    plan = build_arena_recovery_plan(
        result,
        known_scenarios={"existing_vanilla_repair"},
    )

    assert plan["decision"] == "blocked"
    assert plan["strategy"] == "manual_investigation"
    assert plan["execution_available"] is False
    assert plan["command_preview"] is None


def test_recovery_plan_endpoint_remains_read_only_and_ui_has_gate(tmp_path: Path) -> None:
    result = _result(
        run_id="run-recovery",
        missing_paths=["test/edge-cases.test.js"],
    )
    database = tmp_path / "arena-live-recovery.db"
    _write_run(database, result)
    before = database.read_bytes()

    previous_settings = getattr(app.state, "settings", None)
    app.state.settings = Settings(
        _env_file=None,
        arena_history_directory=tmp_path,
        arena_history_max_databases=20,
    )
    try:
        client = TestClient(app)
        page = client.get("/arena")
        assert page.status_code == 200
        assert "Kurtarma manifesti" in page.text
        assert "/recovery-plan" in page.text
        assert "X-Prometheus-CSRF" in page.text
        assert "fetch('/v1/arena" in page.text
        assert "method:'POST'" in page.text
        assert "/recovery-executions" in page.text
        assert "Onay cümlesini aynen yaz" in page.text

        response = client.get(
            "/v1/arena/runs/run-recovery/recovery-plan"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "ready_for_approval"
        assert body["requires_user_approval"] is True
        assert body["safeguards"]["automatic_execution"] is False

        missing = client.get(
            "/v1/arena/runs/missing/recovery-plan"
        )
        assert missing.status_code == 404
        assert database.read_bytes() == before
    finally:
        if previous_settings is None:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
