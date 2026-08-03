import pathlib
import pytest
from app.arena.event_telemetry import summarize_arena_events
from app.arena.diagnostics import diagnose_arena_run
from app.arena.history import ArenaHistoryReader
from app.arena.models import ArenaResult, ArenaScore
from app.arena.runner import ArenaStore


def test_summarize_arena_events_full_counts_and_notable_limit():
    events = []
    events.append({"type": "deterministic_contract_repair_selected", "path": "src/app.py"})
    events.append({"type": "focused_provider_retry_scheduled", "retry": 1})
    for i in range(45):
        events.append({"type": f"generic_step_{i}"})

    counts, notable = summarize_arena_events(events, notable_limit=10)

    assert counts["deterministic_contract_repair_selected"] == 1
    assert counts["focused_provider_retry_scheduled"] == 1
    assert counts["generic_step_0"] == 1

    last_30_types = [e["type"] for e in events[-30:]]
    assert "deterministic_contract_repair_selected" not in last_30_types

    notable_types = [e["type"] for e in notable]
    assert "deterministic_contract_repair_selected" in notable_types
    assert "focused_provider_retry_scheduled" in notable_types


def test_diagnostics_prefers_event_counts():
    payload = {
        "scenario_id": "fastapi_task_api",
        "run_id": "test-run-1",
        "status": "completed",
        "event_counts": {"focused_provider_retry_scheduled": 1},
        "last_events": [],
    }

    diag = diagnose_arena_run(payload)
    finding_codes = [f["code"] for f in diag.get("findings", [])]
    assert "provider_instability" in finding_codes


def test_diagnostics_reports_deterministic_contract_repair():
    payload = {
        "scenario_id": "fastapi_task_api",
        "run_id": "test-run-2",
        "status": "completed",
        "event_counts": {"deterministic_contract_repair_selected": 1},
        "last_events": [],
    }

    diag = diagnose_arena_run(payload)
    finding_codes = [f["code"] for f in diag.get("findings", [])]
    assert "deterministic_contract_repair" in finding_codes


def test_arena_store_preserves_event_telemetry(tmp_path: pathlib.Path):
    db_path = tmp_path / "arena-test-telemetry.db"
    store = ArenaStore(db_path)

    result = ArenaResult(
        run_id="run-telemetry-001",
        scenario_id="fastapi_task_api",
        scenario_title="FastAPI",
        mission_id="mission-1",
        status="completed",
        failure_reason=None,
        elapsed_seconds=1.25,
        workspace=str(tmp_path),
        approvals_applied=0,
        decisions_answered=0,
        required_paths_ok=True,
        missing_required_paths=[],
        protected_paths_ok=True,
        changed_protected_paths=[],
        baseline_verifications=[],
        verifications=[],
        usage={"events": 2, "total_tokens": 300},
        mission_usage=None,
        task_attempts=1,
        failure_records=0,
        score=ArenaScore(
            total=95,
            completion=40,
            verification=25,
            artifacts=10,
            autonomy=10,
            efficiency=5,
            reliability=5,
        ),
        event_counts={"deterministic_contract_repair_selected": 1, "progress": 10},
        notable_events=[{"type": "deterministic_contract_repair_selected", "path": "src/app.py"}],
    )

    store.record(result)

    reader = ArenaHistoryReader(tmp_path)
    stored_run = reader.get("run-telemetry-001")
    assert stored_run is not None
    assert stored_run.get("event_counts") == {"deterministic_contract_repair_selected": 1, "progress": 10}
    assert stored_run.get("notable_events") == [{"type": "deterministic_contract_repair_selected", "path": "src/app.py"}]
