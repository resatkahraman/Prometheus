import pytest
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.supervisor.execution_receipts import (
    ExecutionReceiptStore,
    ExecutionReceiptError,
    ExecutionReceiptIntegrityError,
    DuplicateExecutionReceiptError,
    compute_canonical_receipt_hash,
    sanitize_receipt_data,
)
from app.supervisor.models import (
    ExecutionReceipt,
    ExecutionReceiptPage,
    ExecutionReceiptIntegrity,
    ExecutionReceiptSummary,
    SupervisorCommand,
)
from app.supervisor.service import SupervisorService
from app.supervisor.store import SupervisorCommandStore


@pytest.fixture
def temp_store_root(tmp_path: Path) -> Path:
    return tmp_path / "supervisor_state"


def test_sanitize_receipt_data():
    raw_input = {
        "api_key": "sk-proj-1234567890abcdef1234567890abcdef",
        "secret_token": "bearer super_secret_pass",
        "nested": {
            "password": "my_password_123",
            "normal": "hello world",
        },
    }
    sanitized = sanitize_receipt_data(raw_input)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["secret_token"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["normal"] == "hello world"


def test_execution_receipt_store_sequence_and_hash_chain(temp_store_root: Path):
    store = ExecutionReceiptStore(root=temp_store_root, persistence_enabled=True)
    mission_id = "test-mission-001"

    now1 = datetime.now(timezone.utc)
    rec1 = store.append(
        mission_id=mission_id,
        execution_kind="tool",
        actor_kind="supervisor",
        actor_id="supervisor-main",
        tool_name="safe_terminal",
        started_at=now1,
        completed_at=now1,
        outcome="succeeded",
        request_summary="Run safe terminal preset",
        input_value={"command": "pytest tests/test_foo.py"},
        result_value={"exit_code": 0},
    )

    assert rec1.sequence == 1
    assert rec1.previous_receipt_hash is None
    assert rec1.receipt_hash.startswith("sha256:")

    now2 = datetime.now(timezone.utc)
    rec2 = store.append(
        mission_id=mission_id,
        execution_kind="worker",
        actor_kind="worker",
        actor_id="coder-agent",
        worker_role="coder",
        started_at=now2,
        completed_at=now2,
        outcome="succeeded",
        request_summary="Execute task 1",
    )

    assert rec2.sequence == 2
    assert rec2.previous_receipt_hash == rec1.receipt_hash
    assert rec2.receipt_hash.startswith("sha256:")

    receipts = store.list_receipts(mission_id=mission_id)
    assert len(receipts) == 2
    assert receipts[0].receipt_id == rec1.receipt_id
    assert receipts[1].receipt_id == rec2.receipt_id


def test_execution_receipt_store_corruption_detection(temp_store_root: Path):
    store = ExecutionReceiptStore(root=temp_store_root, persistence_enabled=True)
    mission_id = "test-mission-corrupt"

    now = datetime.now(timezone.utc)
    rec1 = store.append(
        mission_id=mission_id,
        execution_kind="tool",
        actor_kind="supervisor",
        actor_id="supervisor-main",
        tool_name="safe_terminal",
        started_at=now,
        completed_at=now,
        outcome="succeeded",
        request_summary="Initial step",
    )

    # Tamper with file on disk
    file_path = store._receipt_file_path(mission_id)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    data = json.loads(lines[0])
    data["outcome"] = "tampered"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

    store2 = ExecutionReceiptStore(root=temp_store_root, persistence_enabled=True)
    with pytest.raises(ExecutionReceiptIntegrityError):
        store2.list_receipts(mission_id=mission_id)


@pytest.mark.asyncio
async def test_service_record_execution_receipt(tmp_path: Path):
    receipt_store = ExecutionReceiptStore(root=tmp_path, persistence_enabled=True)
    cmd_store = SupervisorCommandStore(ttl_seconds=3600, max_events=100, database_path=tmp_path / "supervisor.db")
    cmd = SupervisorCommand(id="test-cmd-rec", goal="Test receipt recording", status="ready", plan_text="", tasks=[])
    await cmd_store.put(cmd)

    settings = Settings(workspace_root=tmp_path, supervisor_persistence_enabled=True)
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,   # type: ignore
        execution_receipt_store=receipt_store,
    )
    service.store = cmd_store

    now = datetime.now(timezone.utc)
    rec = await service._record_execution_receipt(
        mission_id="test-cmd-rec",
        execution_kind="tool",
        actor_kind="supervisor",
        actor_id="supervisor-main",
        tool_name="safe_terminal",
        started_at=now,
        completed_at=now,
        outcome="succeeded",
        request_summary="Execute step",
    )

    assert isinstance(rec.receipt_id, str) and len(rec.receipt_id) > 0
    assert rec.sequence == 1
    updated_cmd = await cmd_store.get("test-cmd-rec")
    assert any(ev.type == "execution_receipt_recorded" for ev in updated_cmd.events)


def test_execution_receipt_http_endpoints():
    os.environ["HTTP_REMOTE_ACCESS_ENABLED"] = "false"
    with TestClient(app) as client:
        # Unknown command receipts -> 404
        resp = client.get("/v1/supervisor/commands/nonexistent-cmd-id/execution-receipts")
        assert resp.status_code == 404

        # Unknown receipt -> 404
        resp = client.get("/v1/supervisor/commands/nonexistent-cmd-id/execution-receipts/rec-12345")
        assert resp.status_code == 404
