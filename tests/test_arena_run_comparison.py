from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.arena.comparison import compare_arena_runs
from app.core.config import Settings
from app.main import app


def _result(
    *,
    run_id: str,
    scenario_id: str = "fastapi_task_api",
    status: str,
    score: float,
    elapsed_seconds: float,
    model_calls: int,
    total_tokens: int,
    failure_reason: str | None,
    verification_success: bool,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_title": scenario_id,
        "mission_id": f"mission-{run_id}",
        "status": status,
        "failure_reason": failure_reason,
        "elapsed_seconds": elapsed_seconds,
        "workspace": f"workspace/{run_id}",
        "approvals_applied": 0,
        "decisions_answered": 0,
        "required_paths_ok": verification_success,
        "missing_required_paths": [] if verification_success else ["tests/test_task_api.py"],
        "protected_paths_ok": True,
        "changed_protected_paths": [],
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
            "model_calls": model_calls,
            "total_tokens": total_tokens,
        },
        "mission_usage": None,
        "task_attempts": 2,
        "failure_records": 0 if verification_success else 2,
        "score": {
            "total": score,
            "completion": 40.0 if verification_success else 0.0,
            "verification": 25.0 if verification_success else 0.0,
            "artifacts": 10.0 if verification_success else 5.0,
            "autonomy": 10.0,
            "efficiency": 10.0,
            "reliability": 4.5 if verification_success else 0.0,
        },
        "coordination": {
            "handoff_count": 6 if verification_success else 2,
            "completed_agents": ["backend", "qa"] if verification_success else [],
        },
        "context_compiler": {},
        "handoffs": [],
        "tasks": [
            {
                "id": "TASK-001",
                "assigned_agent": "backend",
                "status": "completed" if verification_success else "rework_required",
            },
            {
                "id": "TASK-002",
                "assigned_agent": "qa",
                "status": "completed" if verification_success else "blocked",
            },
        ],
        "last_events": [],
    }


def _write_runs(path: Path, results: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        for index, result in enumerate(results, start=1):
            usage = result["usage"]
            score = result["score"]
            assert isinstance(usage, dict)
            assert isinstance(score, dict)
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
                    float(index),
                ),
            )
        connection.commit()


def test_compare_arena_runs_detects_delivery_recovery() -> None:
    base = _result(
        run_id="failed-run",
        status="failed",
        score=25.0,
        elapsed_seconds=368.0,
        model_calls=9,
        total_tokens=22_870,
        failure_reason="QA görevi bloklandı.",
        verification_success=False,
    )
    candidate = _result(
        run_id="passing-run",
        status="completed",
        score=95.5,
        elapsed_seconds=412.0,
        model_calls=9,
        total_tokens=21_352,
        failure_reason=None,
        verification_success=True,
    )

    comparison = compare_arena_runs(base, candidate)

    assert comparison["same_scenario"] is True
    assert comparison["verdict"] == "improved"
    assert comparison["quality_outcome"] == "improved"
    assert comparison["failure"]["resolved"] is True
    assert comparison["verifications"]["newly_passing"] == [
        "workspace pytest"
    ]
    metrics = {item["key"]: item for item in comparison["metrics"]}
    assert metrics["score"]["delta"] == 70.5
    assert metrics["elapsed_seconds"]["outcome"] == "regressed"
    assert metrics["total_tokens"]["outcome"] == "improved"
    assert comparison["coordination"]["agents_added"] == ["backend", "qa"]


def test_compare_arena_runs_marks_different_scenarios_not_comparable() -> None:
    base = _result(
        run_id="base",
        scenario_id="fastapi_task_api",
        status="completed",
        score=95.0,
        elapsed_seconds=100.0,
        model_calls=3,
        total_tokens=4_000,
        failure_reason=None,
        verification_success=True,
    )
    candidate = _result(
        run_id="candidate",
        scenario_id="existing_vanilla_repair",
        status="completed",
        score=99.5,
        elapsed_seconds=30.0,
        model_calls=1,
        total_tokens=3_399,
        failure_reason=None,
        verification_success=True,
    )

    comparison = compare_arena_runs(base, candidate)

    assert comparison["same_scenario"] is False
    assert comparison["verdict"] == "not_comparable"
    assert any("farklı senaryolara" in item for item in comparison["highlights"])


def test_arena_compare_endpoint_and_ui_are_read_only(tmp_path: Path) -> None:
    failed = _result(
        run_id="run-failed",
        status="failed",
        score=25.0,
        elapsed_seconds=300.0,
        model_calls=9,
        total_tokens=22_000,
        failure_reason="timeout",
        verification_success=False,
    )
    passing = _result(
        run_id="run-passing",
        status="completed",
        score=95.5,
        elapsed_seconds=250.0,
        model_calls=7,
        total_tokens=18_000,
        failure_reason=None,
        verification_success=True,
    )
    database = tmp_path / "arena-live-comparison.db"
    _write_runs(database, [failed, passing])
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
        assert "Koşuları karşılaştır" in page.text
        assert "X-Prometheus-CSRF" in page.text

        response = client.get(
            "/v1/arena/compare",
            params={
                "base_run_id": "run-failed",
                "candidate_run_id": "run-passing",
            },
        )
        assert response.status_code == 200
        assert response.json()["verdict"] == "improved"

        same = client.get(
            "/v1/arena/compare",
            params={
                "base_run_id": "run-passing",
                "candidate_run_id": "run-passing",
            },
        )
        assert same.status_code == 422

        missing = client.get(
            "/v1/arena/compare",
            params={
                "base_run_id": "missing",
                "candidate_run_id": "run-passing",
            },
        )
        assert missing.status_code == 404
        assert database.read_bytes() == before
    finally:
        if previous_settings is None:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
