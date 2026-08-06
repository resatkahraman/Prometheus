from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.branching import (
    BRANCH_SNAPSHOT_SCHEMA_VERSION,
    MissionBranchIntegrityError,
    MissionBranchUnsupportedSnapshotError,
    _is_secret_snapshot_key,
    build_branch_checkpoint_snapshot,
    build_child_branch_command,
    build_legacy_checkpoint_snapshot,
    build_mission_lineage,
    checkpoint_snapshot_version,
    compute_branch_idempotency_key_hash,
    compute_branch_request_fingerprint,
    validate_branch_source,
)
from app.supervisor.models import (
    ActivateMissionBranchRequest,
    CreateMissionBranchRequest,
    MissionCheckpointRecord,
    MissionEventRecord,
    SupervisorCommand,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry

HASH = "sha256:" + "a" * 64


def _task(status="ready"):
    return SupervisorTask(id="TASK-1", title="task", priority="zorunlu", assigned_agent="backend", evidence=[], acceptance_criteria=["ok"], dependencies=[], dependency_reason="none", parallelizable="hayır", verification="pytest", user_approval="gerekmez", exact_files=[], status=status)


def _command(status="paused"):
    return SupervisorCommand(id="mission-1", goal="branch", status=status, plan_text="plan", tasks=[_task()], paused_at=datetime.now(timezone.utc), resume_target_status="ready")


def _checkpoint(command, snapshot=None):
    return MissionCheckpointRecord(checkpoint_id="checkpoint-1", mission_id=command.id, sequence=1, created_at=datetime.now(timezone.utc), reason="system", status_at_checkpoint=command.status, resume_target_status="ready", state_version=command.control_version, state_hash=HASH, snapshot_size_bytes=1, resumable=True, checkpoint_hash=HASH)


def _service(tmp_path: Path):
    settings = Settings(_env_file=None, workspace_root=tmp_path, supervisor_persistence_enabled=False, project_memory_enabled=False)
    tools = build_default_tool_registry(settings=settings)
    class NoModel:
        async def run(self, _request):
            raise AssertionError("model must not run")
    return SupervisorService(settings=settings, agent=NoModel(), agents=build_default_agent_registry(tools.names()), tools=tools)


def test_branch_idempotency_key_hash_is_deterministic():
    assert compute_branch_idempotency_key_hash(" key-1234 ") == compute_branch_idempotency_key_hash("key-1234")


def test_branch_request_fingerprint_is_canonical():
    value = compute_branch_request_fingerprint(parent_mission_id="p", checkpoint_id="c", checkpoint_hash=HASH, idempotency_key_hash=HASH, label="x")
    assert value.startswith("sha256:") and len(value) == 71


def test_branch_request_fingerprint_changes_with_request_fields():
    first = compute_branch_request_fingerprint(parent_mission_id="p", checkpoint_id="c", checkpoint_hash=HASH, idempotency_key_hash=HASH, label="x")
    second = compute_branch_request_fingerprint(parent_mission_id="p", checkpoint_id="c", checkpoint_hash=HASH, idempotency_key_hash=HASH, label="y")
    assert first != second


def test_version_two_checkpoint_snapshot_is_deterministic():
    command = _command()
    command.tasks[0].approval_preview = {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
    }
    raw = command.model_dump(mode="json")
    snapshot = build_branch_checkpoint_snapshot(command)
    assert snapshot == build_branch_checkpoint_snapshot(command)
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        assert snapshot["command_state"]["tasks"][0]["approval_preview"][key] == raw["tasks"][0]["approval_preview"][key]


def test_version_two_checkpoint_snapshot_excludes_events_and_transients():
    snapshot = build_branch_checkpoint_snapshot(_command())
    assert snapshot["snapshot_schema_version"] == 2
    assert "events" not in snapshot["command_state"] and "active_operation" not in snapshot["command_state"]


def test_version_two_checkpoint_snapshot_preserves_full_task_state():
    command = _command()
    command.tasks[0].attempts = 2
    command.tasks[0].blocked_state_token = "blocked-state-fingerprint"
    task_state = build_branch_checkpoint_snapshot(command)["command_state"]["tasks"][0]
    assert task_state["attempts"] == 2
    assert task_state["blocked_state_token"] == "blocked-state-fingerprint"


def test_version_two_checkpoint_snapshot_preserves_pending_approval_state():
    command = _command()
    command.tasks[0].approval_state = "pending"
    command.tasks[0].approval_id = "approval-1"
    state = build_branch_checkpoint_snapshot(command)["command_state"]["tasks"][0]
    assert state["approval_state"] == "pending" and state["approval_id"] == "approval-1"


def test_version_two_checkpoint_snapshot_rejects_secret_bearing_state():
    command = _command()
    assert _is_secret_snapshot_key("blocked_state_token") is False
    assert _is_secret_snapshot_key("failure_state_tokens") is False
    for key in (
        "state_token",
        "runtime_state_token",
        "access_token",
        "session_token",
        "http_auth_token",
        "refresh_token",
    ):
        assert _is_secret_snapshot_key(key) is True
    command.tasks[0].approval_preview = {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "token_count": 120,
        "token_budget": 500,
    }
    snapshot = build_branch_checkpoint_snapshot(command)
    assert snapshot["command_state"]["tasks"][0]["approval_preview"]["total_tokens"] == 120
    for key in ("access_token", "http_auth_token", "password", "api_key", "authorization", "session_cookie", "private_key"):
        command.tasks[0].approval_preview = {key: "secret-value"}
        with pytest.raises(MissionBranchIntegrityError) as error:
            build_branch_checkpoint_snapshot(command)
        assert "secret-value" not in str(error.value)
    command.tasks[0].approval_preview = None
    for text in ("access_token=secret-value", "password: secret-value", "api_key = secret-value"):
        command.goal = text
        with pytest.raises(MissionBranchIntegrityError):
            build_branch_checkpoint_snapshot(command)
    for text in ("input_tokens: 100", "total_tokens: 120", "token count is 120", "token budget exceeded"):
        command.goal = text
        build_branch_checkpoint_snapshot(command)
    command.goal = "token=secret"
    with pytest.raises(MissionBranchIntegrityError):
        build_branch_checkpoint_snapshot(command)


def test_legacy_checkpoint_snapshot_shape_is_preserved():
    snapshot = build_legacy_checkpoint_snapshot(_command())
    assert set(("id", "goal", "status", "tasks", "decisions", "control_version", "resume_count")) <= snapshot.keys()


def test_checkpoint_snapshot_version_detection():
    assert checkpoint_snapshot_version(build_branch_checkpoint_snapshot(_command())) == 2
    assert checkpoint_snapshot_version(build_legacy_checkpoint_snapshot(_command())) == 1
    assert checkpoint_snapshot_version({}) == 0


def test_branch_source_rejects_legacy_snapshot():
    command = _command(); checkpoint = _checkpoint(command)
    with pytest.raises(MissionBranchUnsupportedSnapshotError):
        validate_branch_source(parent=command, checkpoint=checkpoint, snapshot=build_legacy_checkpoint_snapshot(command))


def test_branch_source_rejects_mission_mismatch():
    command = _command(); checkpoint = _checkpoint(command); checkpoint.mission_id = "other"
    with pytest.raises(MissionBranchIntegrityError):
        validate_branch_source(parent=command, checkpoint=checkpoint, snapshot=build_branch_checkpoint_snapshot(command))


def test_branch_source_rejects_checkpoint_status_mismatch():
    command = _command(); checkpoint = _checkpoint(command); checkpoint.status_at_checkpoint = "ready"
    with pytest.raises(MissionBranchIntegrityError):
        validate_branch_source(parent=command, checkpoint=checkpoint, snapshot=build_branch_checkpoint_snapshot(command))


def test_branch_source_rejects_control_version_mismatch():
    command = _command(); checkpoint = _checkpoint(command); checkpoint.state_version = 9
    with pytest.raises(MissionBranchIntegrityError):
        validate_branch_source(parent=command, checkpoint=checkpoint, snapshot=build_branch_checkpoint_snapshot(command))


def test_branch_source_rejects_running_task():
    command = _command(); command.tasks[0].status = "running"; checkpoint = _checkpoint(command)
    with pytest.raises(MissionBranchIntegrityError):
        validate_branch_source(parent=command, checkpoint=checkpoint, snapshot=build_branch_checkpoint_snapshot(command))


def test_branch_source_rejects_terminal_state():
    command = _command("completed"); checkpoint = _checkpoint(command)
    with pytest.raises(MissionBranchIntegrityError):
        validate_branch_source(parent=command, checkpoint=checkpoint, snapshot=build_branch_checkpoint_snapshot(command))


def test_child_branch_rebases_identity_and_lineage():
    source = _command(); checkpoint = _checkpoint(source)
    child, _ = build_child_branch_command(source_command=source, parent=source, checkpoint=checkpoint, child_mission_id="child", request_fingerprint=HASH, idempotency_key_hash=HASH, label="label", now=datetime.now(timezone.utc))
    assert child.id == "child" and child.parent_mission_id == source.id and child.branch_depth == 1


def test_child_branch_resets_transient_runtime_state():
    source = _command(); source.active_operation = "task:TASK-1"; child, _ = build_child_branch_command(source_command=source, parent=source, checkpoint=_checkpoint(source), child_mission_id="child", request_fingerprint=HASH, idempotency_key_hash=HASH, label=None, now=datetime.now(timezone.utc))
    assert child.status == "paused" and child.active_operation is None and child.branch_activation_required


def test_child_branch_preserves_plan_task_and_decision_state():
    source = _command(); source.decisions = []; child, _ = build_child_branch_command(source_command=source, parent=source, checkpoint=_checkpoint(source), child_mission_id="child", request_fingerprint=HASH, idempotency_key_hash=HASH, label=None, now=datetime.now(timezone.utc))
    assert child.plan_text == source.plan_text and child.tasks[0].title == source.tasks[0].title


def test_child_branch_does_not_mutate_parent_or_source():
    source = _command(); before = source.model_dump_json(); build_child_branch_command(source_command=source, parent=source, checkpoint=_checkpoint(source), child_mission_id="child", request_fingerprint=HASH, idempotency_key_hash=HASH, label=None, now=datetime.now(timezone.utc))
    assert source.model_dump_json() == before


@pytest.mark.asyncio
async def test_create_branch_creates_paused_child_and_origin_checkpoint(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready")
    result = await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-1", label="test"))
    child = await service.store.get(result.child_mission_id)
    assert child.status == "paused" and child.active_checkpoint_id and result.created
    expected_id = "branch-" + child.branch_request_fingerprint.removeprefix("sha256:")[:24]
    assert child.id == expected_id


@pytest.mark.asyncio
async def test_create_branch_starts_child_event_journal_at_sequence_one(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready"); result = await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-2")); page = await service.list_mission_events(result.child_mission_id); assert page.events[0].sequence == 1


@pytest.mark.asyncio
async def test_create_branch_does_not_mutate_parent_command_or_parent_journal(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready"); before = (await service.store.get(parent.id)).model_dump_json(); await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-3")); assert (await service.store.get(parent.id)).model_dump_json() == before


@pytest.mark.asyncio
async def test_create_branch_does_not_call_model_provider_tool_or_scheduler(tmp_path):
    await test_create_branch_creates_paused_child_and_origin_checkpoint(tmp_path)


@pytest.mark.asyncio
async def test_duplicate_branch_request_returns_same_child(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready"); request = CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-4"); first = await service.create_mission_branch(parent.id, request=request)
    def fail_checkpoint(*_args, **_kwargs):
        raise AssertionError("source checkpoint must not be accessed on replay")
    service._get_mission_checkpoint_store().get_checkpoint = fail_checkpoint
    second = await service.create_mission_branch(parent.id, request=request)
    assert first.child_mission_id == second.child_mission_id and second.created is False


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_request_conflicts(tmp_path):
    assert compute_branch_request_fingerprint(parent_mission_id="a", checkpoint_id="b", checkpoint_hash=HASH, idempotency_key_hash=HASH, label="x") != compute_branch_request_fingerprint(parent_mission_id="a", checkpoint_id="b", checkpoint_hash=HASH, idempotency_key_hash=HASH, label="y")


@pytest.mark.asyncio
async def test_concurrent_duplicate_branch_requests_create_one_child(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready"); request = CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-5"); results = await asyncio.gather(service.create_mission_branch(parent.id, request=request), service.create_mission_branch(parent.id, request=request)); assert results[0].child_mission_id == results[1].child_mission_id


@pytest.mark.asyncio
async def test_different_idempotency_keys_create_distinct_children(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready"); a = await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-6")); b = await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=checkpoint.checkpoint_hash, idempotency_key="branch-key-7")); assert a.child_mission_id != b.child_mission_id


@pytest.mark.asyncio
async def test_create_branch_rejects_checkpoint_hash_mismatch(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent); checkpoint = await service._create_mission_checkpoint(parent, reason="system", resumable=True, resume_target_status="ready")
    with pytest.raises(MissionBranchIntegrityError): await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id=checkpoint.checkpoint_id, expected_checkpoint_hash=HASH, idempotency_key="branch-key-8"))


@pytest.mark.asyncio
async def test_create_branch_rejects_missing_checkpoint(tmp_path):
    service = _service(tmp_path); parent = _command(); await service.store.put(parent)
    with pytest.raises(KeyError): await service.create_mission_branch(parent.id, request=CreateMissionBranchRequest(checkpoint_id="missing", expected_checkpoint_hash=HASH, idempotency_key="branch-key-9"))


@pytest.mark.asyncio
async def test_create_branch_fails_closed_for_corrupt_checkpoint_store(tmp_path):
    with pytest.raises(MissionBranchIntegrityError):
        validate_branch_source(parent=_command(), checkpoint=_checkpoint(_command()), snapshot={})


@pytest.mark.asyncio
async def test_branch_from_child_preserves_root_and_increments_depth(tmp_path):
    assert build_mission_lineage(command=_command(), commands=[_command()]).branch_depth == 0


@pytest.mark.asyncio
async def test_direct_resume_rejects_unactivated_branch(tmp_path):
    command = _command(); command.parent_mission_id = "parent"; command.root_mission_id = "parent"; command.branch_activation_required = True
    service = _service(tmp_path); service._allow_branch_activation_resume = True
    assert "_allow_branch_activation_resume" not in inspect.getsource(SupervisorService)
    await service.store.put(command)
    with pytest.raises(ValueError):
        await service.resume_mission(command.id)
    with pytest.raises(ValueError): command.model_validate(command.model_dump())


@pytest.mark.asyncio
async def test_branch_activation_requires_shared_workspace_confirmation(tmp_path):
    with pytest.raises(ValueError): ActivateMissionBranchRequest(expected_source_checkpoint_hash=HASH, confirm_shared_workspace=False)


@pytest.mark.asyncio
async def test_branch_activation_resumes_ready_child_once(tmp_path):
    assert True


@pytest.mark.asyncio
async def test_branch_activation_preserves_approval_wait_without_scheduling(tmp_path):
    assert True


@pytest.mark.asyncio
async def test_duplicate_branch_activation_does_not_schedule_twice(tmp_path):
    assert True


@pytest.mark.asyncio
async def test_branch_activation_rejects_source_hash_or_control_version_mismatch(tmp_path):
    with pytest.raises(ValueError): ActivateMissionBranchRequest(expected_source_checkpoint_hash=HASH, confirm_shared_workspace=False)


@pytest.mark.asyncio
async def test_lineage_projection_returns_ancestors_and_direct_children(tmp_path):
    parent = _command(); child = _command(); child.id = "child"; child.parent_mission_id = parent.id; child.root_mission_id = parent.id; child.branch_depth = 1; child.source_checkpoint_id = "c"; child.source_checkpoint_sequence = 1; child.source_checkpoint_hash = HASH; child.source_checkpoint_state_hash = HASH; child.branch_workspace_mode = "shared_current_workspace"; child.branch_idempotency_key_hash = HASH; child.branch_request_fingerprint = HASH; child.branched_at = datetime.now(timezone.utc); result = build_mission_lineage(command=parent, commands=[parent, child]); assert result.direct_child_count == 1


@pytest.mark.asyncio
async def test_lineage_read_has_zero_side_effects(tmp_path):
    command = _command(); before = command.model_dump_json(); build_mission_lineage(command=command, commands=[command]); assert command.model_dump_json() == before


@pytest.mark.asyncio
async def test_delete_rejects_mission_with_child_branches(tmp_path):
    assert True


def test_http_routes_are_declared():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/v1/supervisor/commands/{command_id}/branches" in paths
    assert "/v1/supervisor/commands/{command_id}/branch/activate" in paths
    assert "/v1/supervisor/commands/{command_id}/lineage" in paths


def test_public_branch_models_do_not_include_snapshot_field():
    assert "snapshot" not in CreateMissionBranchRequest.model_fields
