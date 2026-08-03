from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.arena.diagnostics import diagnose_arena_run
from app.core.config import Settings
from app.main import app


def _result(
    *,
    run_id: str,
    status: str = "completed",
    failure_reason: str | None = None,
    missing_paths: list[str] | None = None,
    changed_protected: list[str] | None = None,
    verification_success: bool = True,
    task_statuses: tuple[str, ...] = ("completed",),
    failure_kind: str | None = None,
    retry_scheduled: bool = False,
    retry_exhausted: bool = False,
    failed_calls: int = 0,
) -> dict[str, object]:
    missing = missing_paths or []
    changed = changed_protected or []
    tasks: list[dict[str, object]] = []
    for index, task_status in enumerate(task_statuses, start=1):
        failure_history: list[dict[str, object]] = []
        if failure_kind and index == 1:
            failure_history.append(
                {
                    "signature": f"sig-{index}",
                    "kind": failure_kind,
                    "summary": failure_kind,
                    "count": 1,
                }
            )
        tasks.append(
            {
                "id": f"TASK-{index:03d}",
                "agent": "backend" if index == 1 else "qa",
                "status": task_status,
                "attempts": 1,
                "failure_history": failure_history,
            }
        )
    events: list[dict[str, object]] = []
    if retry_scheduled:
        events.append(
            {
                "type": "focused_provider_retry_scheduled",
                "message": "retry",
            }
        )
    if retry_exhausted:
        events.append(
            {
                "type": "focused_provider_retry_exhausted",
                "message": "exhausted",
            }
        )
    return {
        "run_id": run_id,
        "scenario_id": "fastapi_task_api",
        "scenario_title": "FastAPI Task API",
        "mission_id": f"mission-{run_id}",
        "status": status,
        "failure_reason": failure_reason,
        "elapsed_seconds": 100.0,
        "workspace": f"workspace/{run_id}",
        "approvals_applied": 0,
        "decisions_answered": 0,
        "required_paths_ok": not missing,
        "missing_required_paths": missing,
        "protected_paths_ok": not changed,
        "changed_protected_paths": changed,
        "baseline_verifications": [],
        "verifications": [
            {
                "name": "workspace pytest",
                "preset": "python_pytest",
                "success": verification_success,
                "exit_code": 0 if verification_success else 1,
                "output": "passed" if verification_success else "failed",
            }
        ],
        "usage": {
            "model_calls": 3,
            "successful_calls": 3 - failed_calls,
            "failed_calls": failed_calls,
            "total_tokens": 4_000,
        },
        "mission_usage": None,
        "task_attempts": len(tasks),
        "failure_records": 1 if failure_kind else 0,
        "score": {
            "total": 95.0 if status == "completed" else 25.0,
            "completion": 40.0 if status == "completed" else 0.0,
            "verification": 25.0 if verification_success else 0.0,
            "artifacts": 10.0 if not missing else 5.0,
            "autonomy": 10.0,
            "efficiency": 10.0,
            "reliability": 0.0,
        },
        "coordination": {
            "handoff_count": 3,
            "completed_agents": ["backend"],
        },
        "context_compiler": {},
        "handoffs": [],
        "tasks": tasks,
        "last_events": events,
    }


def _write_run(path: Path, result: dict[str, object]) -> None:
    usage = result["usage"]
    score = result["score"]
    assert isinstance(usage, dict)
    assert isinstance(score, dict)
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


def test_diagnosis_prioritizes_missing_artifact_flow_failure() -> None:
    diagnosis = diagnose_arena_run(
        _result(
            run_id="missing-qa",
            status="failed",
            failure_reason="Çalıştırılabilir görev kalmadı.",
            missing_paths=["tests/test_task_api.py"],
            verification_success=False,
            task_statuses=("completed", "blocked"),
        )
    )

    assert diagnosis["health"] == "failed"
    assert diagnosis["primary_issue"]["code"] == "missing_artifacts"
    codes = {item["code"] for item in diagnosis["findings"]}
    assert {
        "missing_artifacts",
        "task_flow_blocked",
        "verification_failure",
        "run_failure_reason",
    }.issubset(codes)
    assert diagnosis["signals"]["task_statuses"]["blocked"] == 1


def test_diagnosis_reports_recovered_provider_timeout_as_warning() -> None:
    diagnosis = diagnose_arena_run(
        _result(
            run_id="recovered",
            failure_kind="focused_provider_timeout",
            retry_scheduled=True,
            failed_calls=1,
        )
    )

    assert diagnosis["health"] == "warning"
    assert diagnosis["primary_issue"]["code"] == "provider_retry_recovered"
    assert diagnosis["signals"]["failed_model_calls"] == 1
    assert diagnosis["signals"]["event_types"][
        "focused_provider_retry_scheduled"
    ] == 1


def test_diagnosis_marks_clean_delivery_healthy() -> None:
    diagnosis = diagnose_arena_run(_result(run_id="healthy"))

    assert diagnosis["health"] == "healthy"
    assert diagnosis["primary_issue"]["code"] == "healthy_delivery"
    assert len(diagnosis["findings"]) == 1
    assert diagnosis["recommendations"]


def test_diagnosis_prioritizes_protected_path_violation() -> None:
    diagnosis = diagnose_arena_run(
        _result(
            run_id="scope-breach",
            status="failed",
            failure_reason="Protected path changed.",
            changed_protected=["tests/test_contract.py"],
        )
    )

    assert diagnosis["primary_issue"]["code"] == "scope_violation"
    assert diagnosis["primary_issue"]["severity"] == "critical"
    assert diagnosis["signals"]["changed_protected_paths"] == [
        "tests/test_contract.py"
    ]


def test_diagnosis_endpoint_and_ui_are_read_only(tmp_path: Path) -> None:
    result = _result(
        run_id="run-diagnosis",
        status="failed",
        failure_reason="QA blocked.",
        missing_paths=["tests/test_task_api.py"],
        verification_success=False,
        task_statuses=("completed", "blocked"),
    )
    database = tmp_path / "arena-live-diagnosis.db"
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
        assert "Otomatik teşhis" in page.text
        assert "/diagnosis" in page.text
        assert "X-Prometheus-CSRF" in page.text

        response = client.get(
            "/v1/arena/runs/run-diagnosis/diagnosis"
        )
        assert response.status_code == 200
        assert response.json()["primary_issue"]["code"] == "missing_artifacts"

        missing = client.get("/v1/arena/runs/missing/diagnosis")
        assert missing.status_code == 404
        assert database.read_bytes() == before
    finally:
        if previous_settings is None:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
