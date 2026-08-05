from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.supervisor.event_journal import (
    MissionEventIntegrityError,
    MissionEventJournal,
    MissionEventJournalError,
    canonical_event_kind,
    sanitize_payload,
)
from app.supervisor.models import (
    SupervisorCommand,
    SupervisorEvent,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.supervisor.store import SupervisorCommandStore


def test_journal_appends_strict_sequence_and_hash_chain(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "test-mission-001"

    ev1 = journal.append(
        mission_id=m_id,
        event_type="command_created",
        payload={"command_status": "ready"},
    )
    assert ev1.sequence == 1
    assert ev1.previous_hash is None
    assert ev1.event_hash.startswith("sha256:")

    ev2 = journal.append(
        mission_id=m_id,
        event_type="task_started",
        task_id="task-1",
        payload={"command_status": "running", "task_status": "running"},
    )
    assert ev2.sequence == 2
    assert ev2.previous_hash == ev1.event_hash
    assert ev2.event_hash.startswith("sha256:")

    ev3 = journal.append(
        mission_id=m_id,
        event_type="command_completed",
        payload={"command_status": "completed"},
    )
    assert ev3.sequence == 3
    assert ev3.previous_hash == ev2.event_hash


def test_journal_persists_and_reloads_without_rewriting(tmp_path: Path) -> None:
    journal1 = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "test-mission-persist"

    ev1 = journal1.append(mission_id=m_id, event_type="command_created")
    ev2 = journal1.append(mission_id=m_id, event_type="command_completed")

    journal_file = next((tmp_path / "mission_events").glob("*.jsonl"))
    initial_bytes = journal_file.read_bytes()

    journal2 = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    reloaded = journal2.list_events(mission_id=m_id)
    assert len(reloaded) == 2
    assert reloaded[0].event_hash == ev1.event_hash
    assert reloaded[1].event_hash == ev2.event_hash

    assert journal_file.read_bytes() == initial_bytes


def test_journal_uses_hashed_filename_not_raw_mission_id(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "super_secret_mission_id_12345"
    journal.append(mission_id=m_id, event_type="mission_started")

    files = list((tmp_path / "mission_events").glob("*.jsonl"))
    assert len(files) == 1
    filename = files[0].name
    assert m_id not in filename
    assert len(filename) == 64 + 6


def test_journal_rejects_modified_event_hash(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "tamper-hash-mission"
    journal.append(mission_id=m_id, event_type="command_created")

    journal_file = next((tmp_path / "mission_events").glob("*.jsonl"))
    line = journal_file.read_text(encoding="utf-8").strip()
    data = json.loads(line)
    data["event_hash"] = "sha256:" + "f" * 64
    journal_file.write_text(json.dumps(data) + "\n", encoding="utf-8")

    journal2 = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    with pytest.raises(MissionEventIntegrityError) as exc_info:
        journal2.list_events(mission_id=m_id)
    assert exc_info.value.error_code == "journal_event_hash_mismatch"

    integrity = journal2.verify(mission_id=m_id)
    assert integrity.valid is False
    assert integrity.error_code == "journal_event_hash_mismatch"


def test_journal_rejects_sequence_gap(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "seq-gap-mission"
    journal.append(mission_id=m_id, event_type="command_created")

    journal_file = next((tmp_path / "mission_events").glob("*.jsonl"))
    line1 = journal_file.read_text(encoding="utf-8").strip()
    data1 = json.loads(line1)
    data1["sequence"] = 2

    journal_file.write_text(json.dumps(data1) + "\n", encoding="utf-8")

    journal2 = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    with pytest.raises(MissionEventIntegrityError) as exc_info:
        journal2.list_events(mission_id=m_id)
    assert exc_info.value.error_code == "journal_sequence_gap"


def test_journal_rejects_previous_hash_mismatch(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "prev-hash-mismatch-mission"
    journal.append(mission_id=m_id, event_type="command_created")
    journal.append(mission_id=m_id, event_type="command_started")

    journal_file = next((tmp_path / "mission_events").glob("*.jsonl"))
    lines = journal_file.read_text(encoding="utf-8").strip().split("\n")
    data2 = json.loads(lines[1])
    data2["previous_hash"] = "sha256:" + "a" * 64
    lines[1] = json.dumps(data2)
    journal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    journal2 = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    with pytest.raises(MissionEventIntegrityError) as exc_info:
        journal2.list_events(mission_id=m_id)
    assert exc_info.value.error_code in ("journal_previous_hash_mismatch", "journal_event_hash_mismatch")


def test_journal_rejects_trailing_partial_json_line(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "partial-line-mission"
    journal.append(mission_id=m_id, event_type="command_created")

    journal_file = next((tmp_path / "mission_events").glob("*.jsonl"))
    with open(journal_file, "ab") as f:
        f.write(b'{"incomplete": true')

    journal2 = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    with pytest.raises(MissionEventIntegrityError) as exc_info:
        journal2.list_events(mission_id=m_id)
    assert exc_info.value.error_code == "journal_invalid_json"


def test_journal_sanitizes_secret_fields_without_mutating_input() -> None:
    raw_payload = {
        "api_key": "secret-12345",
        "authorization": "Bearer token-xyz",
        "normal_key": "normal_value",
        "nested": {"password": "pass-abc", "count": 42},
    }
    input_copy = dict(raw_payload)

    clean = sanitize_payload(raw_payload)

    assert raw_payload == input_copy
    assert clean["api_key"] == "[REDACTED]"
    assert clean["authorization"] == "[REDACTED]"
    assert clean["normal_key"] == "normal_value"
    assert clean["nested"]["password"] == "[REDACTED]"
    assert clean["nested"]["count"] == 42


def test_journal_limits_nested_and_large_payloads() -> None:
    deep_dict: dict = {}
    curr = deep_dict
    for i in range(12):
        curr["child"] = {}
        curr = curr["child"]
    curr["leaf"] = "too_deep"

    large_list = list(range(300))
    large_str = "x" * 30000

    payload = {
        "deep": deep_dict,
        "list": large_list,
        "text": large_str,
    }

    clean = sanitize_payload(payload)

    assert len(clean["list"]) == 200
    assert clean["text"].endswith("...[TRUNCATED]")
    assert len(clean["text"]) == 20000 + len("...[TRUNCATED]")


def test_journal_in_memory_mode_works_when_persistence_disabled() -> None:
    journal = MissionEventJournal(root=None, persistence_enabled=False)
    m_id = "in-mem-mission"

    e1 = journal.append(mission_id=m_id, event_type="command_created")
    e2 = journal.append(mission_id=m_id, event_type="command_completed")

    events = journal.list_events(mission_id=m_id)
    assert len(events) == 2
    assert events[0].event_id == e1.event_id
    assert events[1].event_id == e2.event_id

    integrity = journal.verify(mission_id=m_id)
    assert integrity.valid is True
    assert integrity.event_count == 2


def test_journal_projection_rebuilds_status_tasks_and_approvals(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "projection-mission"

    journal.append(
        mission_id=m_id,
        event_type="command_created",
        payload={"command_status": "ready"},
    )
    journal.append(
        mission_id=m_id,
        event_type="task_started",
        task_id="t1",
        payload={"command_status": "running", "task_status": "running"},
    )
    journal.append(
        mission_id=m_id,
        event_type="task_approval_requested",
        task_id="t1",
        approval_id="appr-1",
        payload={"command_status": "awaiting_approval", "pending_approval_ids": ["appr-1"]},
    )
    journal.append(
        mission_id=m_id,
        event_type="command_completed",
        payload={"command_status": "completed", "pending_approval_ids": []},
    )

    proj = journal.project_state(mission_id=m_id)
    assert proj.mission_id == m_id
    assert proj.event_count == 4
    assert proj.command_status == "completed"
    assert proj.task_statuses.get("t1") == "running"
    assert proj.pending_approval_ids == []
    assert proj.terminal is True


@pytest.mark.parametrize(
    "event_type,expected_kind",
    [
        ("approval_requested", "approval"),
        ("task_approval_requested", "approval"),
        ("checkpoint_created", "checkpoint"),
        ("recovery_started", "recovery"),
        ("tool_completed", "tool"),
        ("task_started", "step"),
        ("planning_completed", "plan"),
        ("command_completed", "mission"),
        ("unknown_event", "system"),
    ],
)
def test_canonical_event_kind_mapping(event_type: str, expected_kind: str) -> None:
    assert canonical_event_kind(event_type) == expected_kind


@pytest.mark.asyncio
async def test_emit_event_preserves_command_events_and_appends_journal(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    cmd = SupervisorCommand(
        id="service-emit-cmd",
        goal="Test emit event",
        status="ready",
        plan_text="",
        tasks=[],
    )

    SupervisorService._event(
        cmd,
        type="command_started",
        message="Command started",
        data={"test": 123},
    )

    assert len(cmd.events) == 1
    assert cmd.events[0].sequence == 1
    assert cmd.events[0].type == "command_started"
    assert cmd.events[0].message == "Command started"


@pytest.mark.asyncio
async def test_journal_failure_stops_event_flow_fail_closed(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    (tmp_path / "mission_events").rmdir()
    (tmp_path / "mission_events").touch()

    with pytest.raises(MissionEventJournalError):
        journal.append(mission_id="fail-closed-cmd", event_type="command_created")


@pytest.mark.asyncio
async def test_service_lists_real_journal_without_model_or_usage_mutation(tmp_path: Path) -> None:
    settings = Settings(
        workspace_root=tmp_path / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=tmp_path / "supervisor.db",
        http_remote_access_enabled=False,
    )
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    journal.append(mission_id="service-read-cmd", event_type="command_created")

    store = SupervisorCommandStore(
        ttl_seconds=3600,
        max_events=100,
        database_path=tmp_path / "supervisor.db",
    )
    cmd = SupervisorCommand(
        id="service-read-cmd",
        goal="Read test",
        status="ready",
        plan_text="",
        tasks=[],
    )
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = settings
    service._event_journal = journal

    page = await service.list_mission_events("service-read-cmd")
    assert page.source == "journal"
    assert page.integrity_verified is True
    assert len(page.events) == 1
    assert page.events[0].event_type == "command_created"


@pytest.mark.asyncio
async def test_service_falls_back_to_legacy_command_events_read_only(tmp_path: Path) -> None:
    store = SupervisorCommandStore(
        ttl_seconds=3600,
        max_events=100,
        database_path=tmp_path / "supervisor.db",
    )
    cmd = SupervisorCommand(
        id="legacy-cmd-001",
        goal="Legacy test",
        status="running",
        plan_text="",
        tasks=[],
        events=[
            SupervisorEvent(sequence=1, type="command_created", message="Created"),
            SupervisorEvent(sequence=2, type="task_started", message="Task 1", task_id="t1"),
        ],
    )
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "workspace",
        supervisor_persistence_enabled=False,
        http_remote_access_enabled=False,
    )

    page = await service.list_mission_events("legacy-cmd-001")
    assert page.source == "legacy_command_events"
    assert page.integrity_verified is False
    assert len(page.events) == 2
    assert page.events[0].sequence == 1
    assert page.events[0].canonical_kind == "mission"
    assert page.events[1].sequence == 2
    assert page.events[1].canonical_kind == "step"


@pytest.mark.asyncio
async def test_service_does_not_create_journal_for_legacy_read(tmp_path: Path) -> None:
    store = SupervisorCommandStore(
        ttl_seconds=3600,
        max_events=100,
        database_path=tmp_path / "supervisor.db",
    )
    cmd = SupervisorCommand(
        id="legacy-no-disk-cmd",
        goal="No disk test",
        status="ready",
        plan_text="",
        tasks=[],
        events=[SupervisorEvent(sequence=1, type="command_created", message="Created")],
    )
    await store.put(cmd)

    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service._event_journal = journal

    assert journal.has_journal(mission_id="legacy-no-disk-cmd") is False
    page = await service.list_mission_events("legacy-no-disk-cmd")
    assert page.source == "legacy_command_events"
    assert journal.has_journal(mission_id="legacy-no-disk-cmd") is False


@pytest.mark.asyncio
async def test_service_pages_events_in_sequence_order(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    m_id = "page-seq-cmd"
    for i in range(1, 6):
        journal.append(mission_id=m_id, event_type=f"step_{i}")

    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id=m_id, goal="Page seq test", status="ready", plan_text="", tasks=[])
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service._event_journal = journal

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    p1 = await service.list_mission_events(m_id, after_sequence=0, limit=2)
    assert p1.count == 2
    assert [e.sequence for e in p1.events] == [1, 2]
    assert p1.has_more is True
    assert p1.next_after_sequence == 2

    p2 = await service.list_mission_events(m_id, after_sequence=2, limit=2)
    assert p2.count == 2
    assert [e.sequence for e in p2.events] == [3, 4]
    assert p2.has_more is True
    assert p2.next_after_sequence == 4


def _create_test_client() -> TestClient:
    client = TestClient(app)
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    client.headers["X-Prometheus-CSRF"] = "1"
    return client


@pytest.fixture(autouse=True)
def _restore_app_state():
    old_supervisor = getattr(app.state, "supervisor", None)
    yield
    if old_supervisor is not None:
        app.state.supervisor = old_supervisor


@pytest.mark.asyncio
async def test_mission_events_endpoint_returns_real_journal(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    journal.append(mission_id="api-real-cmd", event_type="command_created")

    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id="api-real-cmd", goal="API real test", status="ready", plan_text="", tasks=[])
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "ws",
        supervisor_persistence_enabled=True,
        http_remote_access_enabled=False,
    )
    service._event_journal = journal

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    app.state.supervisor = service
    client = _create_test_client()

    res = client.get("/v1/supervisor/commands/api-real-cmd/mission-events")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "journal"
    assert data["integrity_verified"] is True
    assert len(data["events"]) == 1


@pytest.mark.asyncio
async def test_mission_events_endpoint_returns_legacy_fallback(tmp_path: Path) -> None:
    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(
        id="api-legacy-cmd",
        goal="API legacy test",
        status="ready",
        plan_text="",
        tasks=[],
        events=[SupervisorEvent(sequence=1, type="command_created", message="Created")],
    )
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "ws",
        supervisor_persistence_enabled=False,
        http_remote_access_enabled=False,
    )

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    app.state.supervisor = service
    client = _create_test_client()

    res = client.get("/v1/supervisor/commands/api-legacy-cmd/mission-events")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "legacy_command_events"
    assert data["integrity_verified"] is False


@pytest.mark.asyncio
async def test_mission_events_endpoint_validates_pagination(tmp_path: Path) -> None:
    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id="api-page-cmd", goal="Page val test", status="ready", plan_text="", tasks=[])
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "ws",
        supervisor_persistence_enabled=False,
        http_remote_access_enabled=False,
    )

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    app.state.supervisor = service
    client = _create_test_client()

    assert client.get("/v1/supervisor/commands/api-page-cmd/mission-events?after_sequence=-1").status_code == 422
    assert client.get("/v1/supervisor/commands/api-page-cmd/mission-events?limit=1000").status_code == 422


@pytest.mark.asyncio
async def test_mission_events_endpoint_hides_journal_paths(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    journal.append(mission_id="api-path-cmd", event_type="command_created")

    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id="api-path-cmd", goal="Path hide test", status="ready", plan_text="", tasks=[])
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "ws",
        supervisor_persistence_enabled=True,
        http_remote_access_enabled=False,
    )
    service._event_journal = journal

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    app.state.supervisor = service
    client = _create_test_client()

    res = client.get("/v1/supervisor/commands/api-path-cmd/mission-events")
    body = res.text
    assert str(tmp_path) not in body
    assert "mission_events" not in body


@pytest.mark.asyncio
async def test_mission_events_endpoint_returns_409_on_corruption(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    journal.append(mission_id="api-corrupt-cmd", event_type="command_created")

    journal_file = next((tmp_path / "mission_events").glob("*.jsonl"))
    journal_file.write_text("corrupted_invalid_json_line\n", encoding="utf-8")

    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id="api-corrupt-cmd", goal="Corrupt test", status="ready", plan_text="", tasks=[])
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "ws",
        supervisor_persistence_enabled=True,
        http_remote_access_enabled=False,
    )
    service._event_journal = journal

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    app.state.supervisor = service
    client = _create_test_client()

    res = client.get("/v1/supervisor/commands/api-corrupt-cmd/mission-events")
    assert res.status_code == 409
    assert "bütünlüğü doğrulanamadı" in res.json()["detail"]


@pytest.mark.asyncio
async def test_mission_state_endpoint_replays_projection(tmp_path: Path) -> None:
    journal = MissionEventJournal(root=tmp_path, persistence_enabled=True)
    journal.append(
        mission_id="api-proj-cmd",
        event_type="command_started",
        payload={"command_status": "running"},
    )

    store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id="api-proj-cmd", goal="Proj test", status="running", plan_text="", tasks=[])
    await store.put(cmd)

    service = SupervisorService.__new__(SupervisorService)
    service.store = store
    service.settings = Settings(
        workspace_root=tmp_path / "ws",
        supervisor_persistence_enabled=True,
        http_remote_access_enabled=False,
    )
    service._event_journal = journal

    async def _mock_get(cmd_id: str):
        return await store.get(cmd_id)

    service.get = _mock_get

    app.state.supervisor = service
    client = _create_test_client()

    res = client.get("/v1/supervisor/commands/api-proj-cmd/mission-state")
    assert res.status_code == 200
    data = res.json()
    assert data["mission_id"] == "api-proj-cmd"
    assert data["event_count"] == 1
    assert data["command_status"] == "running"
    assert data["terminal"] is False
