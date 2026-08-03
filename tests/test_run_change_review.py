import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.run_snapshots import RunSnapshotManager


def make_task(task_id: str = "task_001", title: str = "Task", exact_files: list[str] | None = None, verification: str = "pytest") -> SupervisorTask:
    return SupervisorTask(
        id=task_id,
        title=title,
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["Kriter"],
        dependencies=[],
        dependency_reason="Yok",
        parallelizable="evet",
        verification=verification,
        user_approval="gerekmez",
        exact_files=exact_files or [],
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    mgr = RunSnapshotManager(storage_root=snapshots_dir)

    with TestClient(app) as c:
        c.headers["X-Requested-With"] = "XMLHttpRequest"
        c.headers["X-Prometheus-CSRF"] = "1"
        monkeypatch.setattr(app.state.supervisor, "snapshot_manager", mgr)
        import asyncio

        async def clear_store():
            try:
                cmds = await app.state.supervisor.store.list()
                for cmd in cmds:
                    cmd.archived = True
                    cmd.status = "completed"
                    await app.state.supervisor.store.put(cmd)
            except Exception:
                pass

        asyncio.run(clear_store())
        yield c


def test_snapshot_captured_before_execution_and_retry_preserves_first(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    sample_file = ws_root / "sample.txt"
    sample_file.write_text("v1 content", encoding="utf-8")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")

    mgr.capture_task_snapshot(
        command_id="cmd_001",
        task_id="task_001",
        workspace_path=".",
        exact_files=["sample.txt"],
        workspace_root=ws_root,
    )

    sample_file.write_text("v2 content modified", encoding="utf-8")

    mgr.capture_task_snapshot(
        command_id="cmd_001",
        task_id="task_001",
        workspace_path=".",
        exact_files=["sample.txt"],
        workspace_root=ws_root,
    )

    v1_sha = hashlib.sha256(b"v1 content").hexdigest()
    cmd = SupervisorCommand(
        id="cmd_001",
        goal="Test goal",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["sample.txt"])],
    )

    changes = mgr.build_command_change_review(command=cmd, workspace_root=ws_root)
    assert len(changes) == 1
    assert changes[0].sha256_before == v1_sha
    assert changes[0].change_type == "modified"


def test_added_modified_deleted_change_calculation(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    f_mod = ws_root / "mod.txt"
    f_mod.write_text("before mod", encoding="utf-8")

    f_del = ws_root / "del.txt"
    f_del.write_text("before del", encoding="utf-8")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")

    mgr.capture_task_snapshot(
        command_id="cmd_002",
        task_id="task_001",
        workspace_path=".",
        exact_files=["mod.txt", "del.txt", "add.txt"],
        workspace_root=ws_root,
    )

    f_mod.write_text("after mod text", encoding="utf-8")
    f_del.unlink()
    (ws_root / "add.txt").write_text("after add text", encoding="utf-8")

    cmd = SupervisorCommand(
        id="cmd_002",
        goal="Test goal",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["mod.txt", "del.txt", "add.txt"])],
    )

    changes = mgr.build_command_change_review(command=cmd, workspace_root=ws_root)
    change_map = {c.relative_path: c for c in changes}

    assert change_map["mod.txt"].change_type == "modified"
    assert change_map["del.txt"].change_type == "deleted"
    assert change_map["add.txt"].change_type == "added"


def test_binary_file_does_not_produce_text_diff(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    bin_file = ws_root / "data.bin"
    bin_file.write_bytes(b"\x00\xFF\x00\xFF binary data")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")
    mgr.capture_task_snapshot(
        command_id="cmd_bin",
        task_id="task_001",
        workspace_path=".",
        exact_files=["data.bin"],
        workspace_root=ws_root,
    )

    bin_file.write_bytes(b"\x00\xFF\x00\xFF binary data modified")

    cmd = SupervisorCommand(
        id="cmd_bin",
        goal="Binary test",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["data.bin"])],
    )

    changes = mgr.build_command_change_review(command=cmd, workspace_root=ws_root)
    assert changes[0].text_diff_preview is None


def test_sensitive_path_or_root_escape_rejected_in_snapshot(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")

    with pytest.raises(ValueError, match="Sensitive veya geçersiz"):
        mgr.capture_task_snapshot(
            command_id="cmd_esc",
            task_id="task_001",
            workspace_path=".",
            exact_files=["../../secret.txt"],
            workspace_root=ws_root,
        )

    with pytest.raises(ValueError, match="Sensitive veya geçersiz"):
        mgr.capture_task_snapshot(
            command_id="cmd_env",
            task_id="task_001",
            workspace_path=".",
            exact_files=[".env"],
            workspace_root=ws_root,
        )


def test_safe_revert_restores_modified_deleted_and_removes_added(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    f_mod = ws_root / "mod.txt"
    f_mod.write_text("orig mod", encoding="utf-8")

    f_del = ws_root / "del.txt"
    f_del.write_text("orig del", encoding="utf-8")

    unrelated = ws_root / "unrelated.txt"
    unrelated.write_text("don't touch me", encoding="utf-8")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")
    mgr.capture_task_snapshot(
        command_id="cmd_rev",
        task_id="task_001",
        workspace_path=".",
        exact_files=["mod.txt", "del.txt", "add.txt"],
        workspace_root=ws_root,
    )

    f_mod.write_text("run modified this", encoding="utf-8")
    f_del.unlink()
    f_add = ws_root / "add.txt"
    f_add.write_text("run added this", encoding="utf-8")

    mgr.record_task_completion_snapshot(
        command_id="cmd_rev",
        task_id="task_001",
        workspace_root=ws_root,
    )

    cmd = SupervisorCommand(
        id="cmd_rev",
        goal="Revert test",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["mod.txt", "del.txt", "add.txt"])],
    )

    res = mgr.revert_command_changes(
        command=cmd,
        workspace_root=ws_root,
        confirmation="REVERT cmd_rev",
    )

    assert set(res.reverted) == {"mod.txt", "del.txt", "add.txt"}
    assert len(res.conflicts) == 0

    assert f_mod.read_text("utf-8") == "orig mod"
    assert f_del.read_text("utf-8") == "orig del"
    assert not f_add.exists()
    assert unrelated.read_text("utf-8") == "don't touch me"


def test_hash_mismatch_prevents_overwrite_and_reports_conflict(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    f_mod = ws_root / "mod.txt"
    f_mod.write_text("orig mod", encoding="utf-8")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")
    mgr.capture_task_snapshot(
        command_id="cmd_conflict",
        task_id="task_001",
        workspace_path=".",
        exact_files=["mod.txt"],
        workspace_root=ws_root,
    )

    # Run modified it
    f_mod.write_text("run modified", encoding="utf-8")
    mgr.record_task_completion_snapshot(
        command_id="cmd_conflict",
        task_id="task_001",
        workspace_root=ws_root,
    )

    cmd = SupervisorCommand(
        id="cmd_conflict",
        goal="Conflict test",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["mod.txt"])],
    )

    # User manually edited it after run
    f_mod.write_text("user manual edit after run", encoding="utf-8")

    res = mgr.revert_command_changes(
        command=cmd,
        workspace_root=ws_root,
        confirmation="REVERT cmd_conflict",
    )

    assert "mod.txt" in res.conflicts
    assert f_mod.read_text("utf-8") == "user manual edit after run"


def test_revert_requires_exact_confirmation_and_terminal_status(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    f_mod = ws_root / "mod.txt"
    f_mod.write_text("orig", encoding="utf-8")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")
    mgr.capture_task_snapshot(
        command_id="cmd_nonterm",
        task_id="task_001",
        workspace_path=".",
        exact_files=["mod.txt"],
        workspace_root=ws_root,
    )

    cmd_running = SupervisorCommand(
        id="cmd_nonterm",
        goal="Running cmd",
        status="running",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["mod.txt"])],
    )

    with pytest.raises(ValueError, match="Confirmation uyuşmuyor"):
        mgr.revert_command_changes(command=cmd_running, workspace_root=ws_root, confirmation="WRONG")

    with pytest.raises(ValueError, match="tamamlanmış"):
        mgr.revert_command_changes(command=cmd_running, workspace_root=ws_root, confirmation="REVERT cmd_nonterm")


def test_second_revert_is_idempotent(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    f_mod = ws_root / "mod.txt"
    f_mod.write_text("orig", encoding="utf-8")

    mgr = RunSnapshotManager(storage_root=tmp_path / "snaps")
    mgr.capture_task_snapshot(
        command_id="cmd_idem",
        task_id="task_001",
        workspace_path=".",
        exact_files=["mod.txt"],
        workspace_root=ws_root,
    )

    f_mod.write_text("modified by run", encoding="utf-8")
    mgr.record_task_completion_snapshot(
        command_id="cmd_idem",
        task_id="task_001",
        workspace_root=ws_root,
    )

    cmd = SupervisorCommand(
        id="cmd_idem",
        goal="Idem test",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["mod.txt"])],
    )

    res1 = mgr.revert_command_changes(command=cmd, workspace_root=ws_root, confirmation="REVERT cmd_idem")
    assert "mod.txt" in res1.reverted

    res2 = mgr.revert_command_changes(command=cmd, workspace_root=ws_root, confirmation="REVERT cmd_idem")
    assert "mod.txt" in res2.skipped


def test_change_review_endpoint(client, monkeypatch):
    cmd = SupervisorCommand(
        id="cmd_api_review",
        goal="API test",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["app/main.py"], verification="pytest")],
    )

    async def mock_get(cmd_id):
        return cmd

    monkeypatch.setattr(app.state.supervisor.store, "get", mock_get)

    res = client.get("/v1/supervisor/commands/cmd_api_review/change-review")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["command_id"] == "cmd_api_review"
    assert data["status"] == "completed"
    assert data["terminal"] is True
    assert "revert_confirmation" in data
    assert data["revert_confirmation"] == "REVERT cmd_api_review"


def test_revert_endpoint(client, monkeypatch):
    cmd = SupervisorCommand(
        id="cmd_api_revert",
        goal="API revert test",
        status="completed",
        plan_text="Plan",
        tasks=[make_task("task_001", exact_files=["app/main.py"])],
    )

    async def mock_get(cmd_id):
        return cmd

    async def mock_put(command):
        pass

    monkeypatch.setattr(app.state.supervisor.store, "get", mock_get)
    monkeypatch.setattr(app.state.supervisor.store, "put", mock_put)

    app.state.supervisor.snapshot_manager.capture_task_snapshot(
        command_id="cmd_api_revert",
        task_id="task_001",
        workspace_path=".",
        exact_files=["app/main.py"],
        workspace_root=app.state.supervisor.settings.workspace_root,
    )

    res = client.post(
        "/v1/supervisor/commands/cmd_api_revert/revert",
        json={"confirmation": "REVERT cmd_api_revert"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["command_id"] == "cmd_api_revert"
    assert data["event_recorded"] is True
