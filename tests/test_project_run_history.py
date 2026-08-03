import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.supervisor.models import SupervisorCommand, SupervisorTask


@pytest.fixture
def client(tmp_path):
    with TestClient(app) as c:
        c.headers["X-Requested-With"] = "XMLHttpRequest"
        c.headers["X-Prometheus-CSRF"] = "1"
        yield c


@pytest.mark.asyncio
async def test_list_project_run_history_filters_and_sorting(client):
    supervisor = app.state.supervisor
    store = supervisor.store

    # Legacy command (should be excluded)
    legacy_cmd = SupervisorCommand(
        id="cmd_legacy_001",
        goal="Legacy Goal",
        status="completed",
        plan_text="plan",
        tasks=[],
        project_run_preview_digest=None,
        project_run_workspace_path=None,
    )
    await store.put(legacy_cmd)

    # Project Run command 1 for proj_a
    cmd_a1 = SupervisorCommand(
        id="cmd_a1",
        goal="Feature A1",
        status="completed",
        plan_text="plan",
        tasks=[
            SupervisorTask(
                id="t_a1_1",
                title="Task A1.1",
                priority="high",
                assigned_agent="executor",
                evidence=[],
                acceptance_criteria=[],
                dependencies=[],
                dependency_reason="",
                parallelizable="false",
                verification="python -m pytest",
                user_approval="always",
                exact_files=["a.py"],
                status="completed",
            )
        ],
        project_run_preview_digest="digest_a1",
        project_run_workspace_path="proj_a",
        created_at="2026-08-03T10:00:00Z",
    )
    await store.put(cmd_a1)

    # Project Run command 2 for proj_a (Failed)
    cmd_a2 = SupervisorCommand(
        id="cmd_a2",
        goal="Feature A2",
        status="failed",
        plan_text="plan",
        tasks=[
            SupervisorTask(
                id="t_a2_1",
                title="Task A2.1",
                priority="high",
                assigned_agent="executor",
                evidence=[],
                acceptance_criteria=[],
                dependencies=[],
                dependency_reason="",
                parallelizable="false",
                verification="python -m pytest",
                user_approval="always",
                exact_files=["a2.py"],
                status="failed",
            )
        ],
        project_run_preview_digest="digest_a2",
        project_run_workspace_path="proj_a",
        created_at="2026-08-03T11:00:00Z",
    )
    await store.put(cmd_a2)

    # Query history for proj_a via HTTP endpoint
    res = client.get("/v1/supervisor/project-runs?workspace_path=proj_a&status=all")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["workspace_path"] == "proj_a"
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Newest first
    assert data["items"][0]["command_id"] == "cmd_a2"
    assert data["items"][1]["command_id"] == "cmd_a1"

    # Status filter: failed
    res_failed = client.get("/v1/supervisor/project-runs?workspace_path=proj_a&status=failed")
    assert res_failed.status_code == 200
    data_failed = res_failed.json()
    assert data_failed["total"] == 1
    assert data_failed["items"][0]["command_id"] == "cmd_a2"


@pytest.mark.asyncio
async def test_retry_request_creates_pending_approval_without_executing(client):
    supervisor = app.state.supervisor
    store = supervisor.store

    cmd = SupervisorCommand(
        id="cmd_retry_test",
        goal="Retry Goal",
        status="failed",
        plan_text="plan",
        tasks=[
            SupervisorTask(
                id="t_failed_1",
                title="Failing Task",
                priority="high",
                assigned_agent="executor",
                evidence=[],
                acceptance_criteria=[],
                dependencies=[],
                dependency_reason="",
                parallelizable="false",
                verification="python -m pytest",
                user_approval="always",
                exact_files=["main.py"],
                status="failed",
                attempts=1,
            )
        ],
        project_run_preview_digest="digest_retry",
        project_run_workspace_path=".",
    )
    await store.put(cmd)

    # Request retry via HTTP endpoint
    res = client.post(
        "/v1/supervisor/commands/cmd_retry_test/tasks/t_failed_1/retry-request",
        json={"reason": "Fix syntax error"},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["command_id"] == "cmd_retry_test"
    assert data["task_id"] == "t_failed_1"
    assert data["approval_state"] == "pending"
    assert data["execution_started"] is False
    assert data["model_calls"] == 0
    assert data["total_tokens"] == 0

    # Verify task state in store
    updated_cmd = await store.get("cmd_retry_test")
    task = updated_cmd.tasks[0]
    assert task.status == "awaiting_approval"
    assert task.approval_state == "pending"
    assert task.attempts == 1  # Attempts must NOT be incremented

    # Idempotent replay
    res_replay = client.post(
        "/v1/supervisor/commands/cmd_retry_test/tasks/t_failed_1/retry-request",
        json={"reason": "Fix syntax error"},
    )
    assert res_replay.status_code == 200
    data_replay = res_replay.json()
    assert data_replay["approval_id"] == data["approval_id"]
    assert data_replay["execution_started"] is False
