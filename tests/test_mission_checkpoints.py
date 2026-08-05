import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import Settings
from app.supervisor.checkpoints import (
    MissionCheckpointStore,
    MissionCheckpointError,
    MissionCheckpointIntegrityError,
    DuplicateMissionCheckpointError,
    compute_state_hash,
)
from app.supervisor.models import (
    SupervisorCommand,
    SupervisorTask,
    MissionCheckpointRecord,
    MissionCheckpointPage,
    MissionControlResponse,
)
from app.supervisor.service import SupervisorService


def _make_task(
    *,
    task_id: str,
    title: str,
    status: str,
) -> SupervisorTask:
    return SupervisorTask(
        id=task_id,
        title=title,
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=[],
        status=status,
    )

@pytest.fixture
def temp_checkpoint_root(tmp_path: Path) -> Path:
    root = tmp_path / "supervisor_state"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def temp_checkpoint_store(temp_checkpoint_root: Path) -> MissionCheckpointStore:
    return MissionCheckpointStore(
        root=temp_checkpoint_root,
        persistence_enabled=True,
    )


def test_checkpoint_store_appends_strict_sequence_and_hash_chain(
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "test-mission-seq-1"
    now = datetime.now(timezone.utc)
    snap1 = {"status": "ready", "task_idx": 0}

    rec1 = temp_checkpoint_store.append(
        mission_id=m_id,
        reason="pause_boundary",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status="ready",
        current_task_id="task-1",
        pending_approval_ids=[],
        state_version=1,
        state_snapshot=snap1,
        resumable=True,
    )
    assert rec1.sequence == 1
    assert rec1.previous_checkpoint_hash is None
    assert rec1.checkpoint_hash.startswith("sha256:")

    snap2 = {"status": "ready", "task_idx": 1}
    rec2 = temp_checkpoint_store.append(
        mission_id=m_id,
        reason="pause_boundary",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status="ready",
        current_task_id="task-2",
        pending_approval_ids=[],
        state_version=2,
        state_snapshot=snap2,
        resumable=True,
    )
    assert rec2.sequence == 2
    assert rec2.previous_checkpoint_hash == rec1.checkpoint_hash
    assert rec2.checkpoint_hash.startswith("sha256:")


def test_checkpoint_store_persists_and_reloads_without_rewriting(
    temp_checkpoint_root: Path,
):
    store1 = MissionCheckpointStore(root=temp_checkpoint_root, persistence_enabled=True)
    m_id = "test-mission-reload"
    now = datetime.now(timezone.utc)
    snap = {"status": "ready", "val": 100}

    rec1 = store1.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot=snap,
        resumable=False,
    )

    store2 = MissionCheckpointStore(root=temp_checkpoint_root, persistence_enabled=True)
    recs = store2.list_checkpoints(mission_id=m_id)
    assert len(recs) == 1
    assert recs[0].checkpoint_id == rec1.checkpoint_id
    assert recs[0].checkpoint_hash == rec1.checkpoint_hash


def test_checkpoint_store_uses_hashed_filename_not_raw_mission_id(
    temp_checkpoint_root: Path,
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "raw/mission:id@test"
    now = datetime.now(timezone.utc)
    temp_checkpoint_store.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot={"a": 1},
        resumable=False,
    )

    hashed = hashlib.sha256(m_id.encode("utf-8")).hexdigest()
    expected_file = temp_checkpoint_root / "mission_checkpoints" / f"{hashed}.jsonl"
    assert expected_file.exists()


def test_checkpoint_store_rejects_duplicate_checkpoint_id(
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "dup-check-mission"
    now = datetime.now(timezone.utc)
    c_id = "fixed-check-id"

    temp_checkpoint_store.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot={"x": 1},
        resumable=False,
        checkpoint_id=c_id,
    )

    with pytest.raises(DuplicateMissionCheckpointError):
        temp_checkpoint_store.append(
            mission_id=m_id,
            reason="manual",
            created_at=now,
            status_at_checkpoint="ready",
            resume_target_status=None,
            current_task_id=None,
            pending_approval_ids=[],
            state_version=1,
            state_snapshot={"x": 2},
            resumable=False,
            checkpoint_id=c_id,
        )


def test_checkpoint_store_rejects_modified_state_hash(
    temp_checkpoint_root: Path,
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "corrupt-state-hash-mission"
    now = datetime.now(timezone.utc)
    temp_checkpoint_store.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot={"val": 1},
        resumable=False,
    )

    hashed = hashlib.sha256(m_id.encode("utf-8")).hexdigest()
    filepath = temp_checkpoint_root / "mission_checkpoints" / f"{hashed}.jsonl"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.loads(f.readline())

    data["state_hash"] = "sha256:" + "0" * 64
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

    with pytest.raises(MissionCheckpointIntegrityError):
        temp_checkpoint_store.list_checkpoints(mission_id=m_id)


def test_checkpoint_store_rejects_modified_checkpoint_hash(
    temp_checkpoint_root: Path,
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "corrupt-checkpoint-hash-mission"
    now = datetime.now(timezone.utc)
    temp_checkpoint_store.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot={"val": 1},
        resumable=False,
    )

    hashed = hashlib.sha256(m_id.encode("utf-8")).hexdigest()
    filepath = temp_checkpoint_root / "mission_checkpoints" / f"{hashed}.jsonl"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.loads(f.readline())

    data["checkpoint_hash"] = "sha256:" + "f" * 64
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

    with pytest.raises(MissionCheckpointIntegrityError):
        temp_checkpoint_store.list_checkpoints(mission_id=m_id)


def test_checkpoint_store_rejects_trailing_partial_json_line(
    temp_checkpoint_root: Path,
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "partial-line-mission"
    now = datetime.now(timezone.utc)
    temp_checkpoint_store.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot={"val": 1},
        resumable=False,
    )

    hashed = hashlib.sha256(m_id.encode("utf-8")).hexdigest()
    filepath = temp_checkpoint_root / "mission_checkpoints" / f"{hashed}.jsonl"

    with open(filepath, "ab") as f:
        f.write(b'{"checkpoint_id": "partial')

    with pytest.raises(MissionCheckpointIntegrityError):
        temp_checkpoint_store.list_checkpoints(mission_id=m_id)


def test_checkpoint_store_keeps_private_snapshot_out_of_public_record(
    temp_checkpoint_store: MissionCheckpointStore,
):
    m_id = "private-snap-mission"
    now = datetime.now(timezone.utc)
    rec = temp_checkpoint_store.append(
        mission_id=m_id,
        reason="manual",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status=None,
        current_task_id=None,
        pending_approval_ids=[],
        state_version=0,
        state_snapshot={"secret": "super_secret_value"},
        resumable=False,
    )

    assert not hasattr(rec, "state_snapshot")
    rec_dict = rec.model_dump(mode="json")
    assert "state_snapshot" not in rec_dict
    assert "secret" not in json.dumps(rec_dict)


def test_checkpoint_store_in_memory_mode_matches_disk_semantics():
    mem_store = MissionCheckpointStore(root=None, persistence_enabled=False)
    m_id = "in-mem-mission"
    now = datetime.now(timezone.utc)

    rec1 = mem_store.append(
        mission_id=m_id,
        reason="pause_boundary",
        created_at=now,
        status_at_checkpoint="ready",
        resume_target_status="ready",
        current_task_id=None,
        pending_approval_ids=[],
        state_version=1,
        state_snapshot={"step": 1},
        resumable=True,
    )
    assert rec1.sequence == 1

    recs = mem_store.list_checkpoints(mission_id=m_id)
    assert len(recs) == 1
    assert recs[0].checkpoint_hash == rec1.checkpoint_hash

    snap = mem_store.get_checkpoint_snapshot(mission_id=m_id, checkpoint_id=rec1.checkpoint_id)
    assert snap == {"step": 1}


def test_checkpoint_snapshot_is_deterministic():
    snap1 = {"b": 2, "a": 1, "nested": {"y": [1, 2], "x": True}}
    snap2 = {"nested": {"x": True, "y": [1, 2]}, "a": 1, "b": 2}

    h1, s1 = compute_state_hash(snap1)
    h2, s2 = compute_state_hash(snap2)

    assert h1 == h2
    assert s1 == s2


@pytest.mark.asyncio
async def test_pause_request_sets_persistent_cooperative_flag(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-pause-1",
        goal="Test pause request",
        status="running",
        plan_text="Step 1",
        tasks=[
            _make_task(task_id="task-1", title="Task 1", status="running"),
        ],
    )
    await service.store.put(cmd)

    resp = await service.request_mission_pause("cmd-pause-1", reason="Need inspection")
    assert resp.pause_requested is True
    assert resp.command_status == "running"

    updated = await service.store.get("cmd-pause-1")
    assert updated.pause_requested is True
    assert updated.pause_reason == "Need inspection"


@pytest.mark.asyncio
async def test_duplicate_pause_request_is_idempotent(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-pause-idemp",
        goal="Test duplicate pause",
        status="running",
        plan_text="Step 1",
        tasks=[_make_task(task_id="task-1", title="Task 1", status="running")],
    )
    await service.store.put(cmd)

    resp1 = await service.request_mission_pause("cmd-pause-idemp", reason="First")
    resp2 = await service.request_mission_pause("cmd-pause-idemp", reason="Second")

    assert resp1.pause_requested is True
    assert resp2.pause_requested is True
    assert resp2.control_version == resp1.control_version


@pytest.mark.asyncio
async def test_pause_request_rejects_terminal_command(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-pause-term",
        goal="Test terminal pause",
        status="completed",
        plan_text="Done",
        tasks=[],
    )
    await service.store.put(cmd)

    with pytest.raises(ValueError, match="Terminal command"):
        await service.request_mission_pause("cmd-pause-term")


@pytest.mark.asyncio
async def test_resume_verifies_active_checkpoint_and_state_hash(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-resume-1",
        goal="Test resume",
        status="ready",
        plan_text="Ready step",
        tasks=[_make_task(task_id="t1", title="T1", status="ready")],
    )
    await service.store.put(cmd)

    # Pause it
    await service.request_mission_pause("cmd-resume-1")
    paused_cmd = await service.store.get("cmd-resume-1")
    assert paused_cmd.status == "paused"
    active_cp_id = paused_cmd.active_checkpoint_id
    assert active_cp_id is not None

    # Resume it
    res_resp = await service.resume_mission("cmd-resume-1", checkpoint_id=active_cp_id)
    assert res_resp.command_status == "ready"
    assert res_resp.active_checkpoint_id is None
    assert res_resp.resume_count == 1

    resumed_cmd = await service.store.get("cmd-resume-1")
    assert resumed_cmd.status == "ready"
    assert resumed_cmd.active_checkpoint_id is None


@pytest.mark.asyncio
async def test_second_resume_does_not_schedule_twice(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-double-resume",
        goal="Test double resume",
        status="ready",
        plan_text="Ready step",
        tasks=[_make_task(task_id="t1", title="T1", status="ready")],
    )
    await service.store.put(cmd)
    await service.request_mission_pause("cmd-double-resume")

    paused_cmd = await service.store.get("cmd-double-resume")
    active_cp_id = paused_cmd.active_checkpoint_id

    await service.resume_mission("cmd-double-resume", checkpoint_id=active_cp_id)

    # Attempting second resume should fail because command is no longer paused
    with pytest.raises(ValueError, match="paused durumunda değil"):
        await service.resume_mission("cmd-double-resume", checkpoint_id=active_cp_id)


@pytest.mark.asyncio
async def test_manual_checkpoint_at_safe_boundary_is_non_resumable(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-manual-cp",
        goal="Test manual checkpoint",
        status="ready",
        plan_text="Ready step",
        tasks=[_make_task(task_id="t1", title="T1", status="ready")],
    )
    await service.store.put(cmd)

    rec = await service.create_mission_checkpoint("cmd-manual-cp")
    assert rec.reason == "manual"
    assert rec.resumable is False

    cmd_after = await service.store.get("cmd-manual-cp")
    assert cmd_after.status == "ready"  # status unchanged


@pytest.mark.asyncio
async def test_checkpoint_read_services_have_zero_side_effects(
    temp_checkpoint_root: Path,
):
    settings = Settings(
        workspace_root=temp_checkpoint_root / "workspace",
        supervisor_persistence_enabled=True,
        supervisor_database_path=temp_checkpoint_root / "supervisor.db",
    )
    service = SupervisorService(
        settings=settings,
        agent=None,  # type: ignore
        agents=None,  # type: ignore
        tools=None,  # type: ignore
    )
    cmd = SupervisorCommand(
        id="cmd-read-side-effects",
        goal="Test read side effects",
        status="ready",
        plan_text="Ready step",
        tasks=[],
    )
    await service.store.put(cmd)

    page = await service.list_mission_checkpoints("cmd-read-side-effects")
    assert page.count == 0
    assert page.source == "empty"

    # Ensure no disk file was created for an empty read
    hashed = hashlib.sha256("cmd-read-side-effects".encode("utf-8")).hexdigest()
    cp_file = temp_checkpoint_root / "mission_checkpoints" / f"{hashed}.jsonl"
    assert not cp_file.exists()
