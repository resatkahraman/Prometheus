from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.arena.history import ArenaHistoryReader
from app.core.config import Settings
from app.main import app


def _write_db(
    path: Path,
    *,
    run_id: str,
    scenario_id: str,
    status: str,
    score: float,
    created_at: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_title": f"Title {scenario_id}",
        "mission_id": "mission-1",
        "status": status,
        "failure_reason": None,
        "elapsed_seconds": 12.5,
        "workspace": "workspace/example",
        "approvals_applied": 0,
        "decisions_answered": 0,
        "required_paths_ok": True,
        "missing_required_paths": [],
        "protected_paths_ok": True,
        "changed_protected_paths": [],
        "baseline_verifications": [],
        "verifications": [],
        "usage": {"model_calls": 3, "total_tokens": 1200},
        "mission_usage": None,
        "task_attempts": 1,
        "failure_records": 0,
        "score": {"total": score},
        "coordination": {},
        "context_compiler": {},
        "handoffs": [],
        "tasks": [],
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
                run_id, scenario_id, "mission-1", status, score, 12.5,
                3, 1200, 0, 0, json.dumps(payload), created_at,
            ),
        )
        connection.commit()


def test_reader_aggregates_filters_and_reads_details(tmp_path: Path) -> None:
    _write_db(
        tmp_path / "arena.db",
        run_id="run-old",
        scenario_id="alpha",
        status="failed",
        score=20.0,
        created_at=10.0,
    )
    _write_db(
        tmp_path / "arena-live.db",
        run_id="run-new",
        scenario_id="beta",
        status="completed",
        score=95.0,
        created_at=20.0,
    )
    (tmp_path / "arena-corrupt.db").write_text("not sqlite", encoding="utf-8")
    (tmp_path / "unrelated.db").write_text("ignored", encoding="utf-8")

    reader = ArenaHistoryReader(tmp_path)
    history = reader.history(limit=10)

    assert [item["run_id"] for item in history] == ["run-new", "run-old"]
    assert reader.history(scenario_id="ALPHA")[0]["run_id"] == "run-old"
    assert reader.get("run-new")["database"] == "arena-live.db"
    assert reader.get("missing") is None


def test_reader_ignores_symlinked_database(tmp_path: Path) -> None:
    outside = tmp_path.parent / "arena-outside.db"
    _write_db(
        outside,
        run_id="outside",
        scenario_id="alpha",
        status="completed",
        score=100.0,
        created_at=30.0,
    )
    link = tmp_path / "arena-link.db"
    try:
        link.symlink_to(outside)
    except OSError:
        return
    assert ArenaHistoryReader(tmp_path).history() == []


def test_arena_dashboard_http_endpoints_are_read_only(tmp_path: Path) -> None:
    _write_db(
        tmp_path / "arena-live-test.db",
        run_id="run-http",
        scenario_id="existing_vanilla_repair",
        status="completed",
        score=99.5,
        created_at=40.0,
    )
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
        assert "Prometheus Arena" in page.text

        scenarios = client.get("/v1/arena/scenarios")
        assert scenarios.status_code == 200
        assert any(
            item["id"] == "existing_vanilla_repair"
            for item in scenarios.json()
        )

        history = client.get("/v1/arena/history?limit=10")
        assert history.status_code == 200
        assert history.json()[0]["run_id"] == "run-http"

        detail = client.get("/v1/arena/runs/run-http")
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"

        missing = client.get("/v1/arena/runs/missing")
        assert missing.status_code == 404
    finally:
        if previous_settings is None:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
