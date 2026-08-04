import os
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.schemas import (
    ProjectRunPreviewRequest,
    ProjectRunCommitRequest,
)
from app.supervisor.service import SupervisorService
from app.main import app


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Init git
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)

    # Initial files
    init_file = repo_dir / "app.py"
    init_file.write_text("def main(): pass\n", encoding="utf-8")

    subprocess.run(["git", "add", "app.py"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

    return repo_dir


from app.agents.registry import build_default_agent_registry
from app.tools.registry import build_default_tool_registry


class FakeAgent:
    async def run(self, request):
        return None


@pytest.fixture
def supervisor_svc(tmp_path):
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    agents = build_default_agent_registry(tools.names())
    return SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=agents,
        tools=tools,
    )


@pytest.mark.asyncio
async def test_workspace_mode_preserves_default(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()
    req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="workspace",
    )
    preview = await supervisor_svc.preview_project_run(req)
    assert preview.execution_mode == "workspace"
    assert preview.git_branch_name is None


@pytest.mark.asyncio
async def test_isolated_preview_does_not_mutate_git(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()
    req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview = await supervisor_svc.preview_project_run(req)
    assert preview.execution_mode == "isolated_branch"
    assert preview.git_is_repository is True
    assert preview.git_base_branch == "main"
    assert preview.git_worktree_clean is True
    assert preview.git_branch_name.startswith("prometheus/run-")

    # Check git branches count - no new branch should exist yet
    res = subprocess.run(["git", "branch"], cwd=str(temp_git_repo), capture_output=True, text=True)
    branches = [b.strip().replace("* ", "") for b in res.stdout.splitlines() if b.strip()]
    assert branches == ["main"]


@pytest.mark.asyncio
async def test_isolated_preview_rejects_dirty_worktree(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()
    dirty_file = temp_git_repo / "uncommitted.txt"
    dirty_file.write_text("dirty content", encoding="utf-8")

    req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    with pytest.raises(ValueError, match="kirli|kaydedilmemiş"):
        await supervisor_svc.preview_project_run(req)


@pytest.mark.asyncio
async def test_isolated_preview_rejects_invalid_branch_name(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()
    with pytest.raises(ValueError, match="geçersiz|karakter"):
        ProjectRunPreviewRequest(
            goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
            workspace_path=rel_path,
            execution_mode="isolated_branch",
            branch_name="feature/../invalid",
        )


@pytest.mark.asyncio
async def test_deterministic_default_branch_name(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()
    req1 = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview1 = await supervisor_svc.preview_project_run(req1)

    req2 = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview2 = await supervisor_svc.preview_project_run(req2)

    assert preview1.git_branch_name == preview2.git_branch_name


@pytest.mark.asyncio
async def test_commit_does_not_create_branch_before_approval(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()
    prev_req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview = await supervisor_svc.preview_project_run(prev_req)

    commit_req = ProjectRunCommitRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        preview_digest=preview.preview_digest,
        execution_mode="isolated_branch",
    )
    commit_res = await supervisor_svc.commit_project_run(commit_req)

    assert commit_res.git_branch_created is False
    assert commit_res.git_commit_hash is None

    # Check git branches in repo - still main only
    res = subprocess.run(["git", "branch"], cwd=str(temp_git_repo), capture_output=True, text=True)
    branches = [b.strip().replace("* ", "") for b in res.stdout.splitlines() if b.strip()]
    assert branches == ["main"]


@pytest.mark.asyncio
async def test_branch_created_and_exact_files_committed_on_successful_run(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()

    prev_req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview = await supervisor_svc.preview_project_run(prev_req)

    commit_req = ProjectRunCommitRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        preview_digest=preview.preview_digest,
        execution_mode="isolated_branch",
    )
    commit_res = await supervisor_svc.commit_project_run(commit_req)

    command = await supervisor_svc.store.get(commit_res.command_id)
    assert command.project_run_git_branch_created is False

    # Simulate approval and task execution
    for task in command.tasks:
        task.approval_state = "approved"

    # Simulate snapshot & task run hook
    first_task = command.tasks[0]
    exact_rel = "app.py"
    first_task.exact_files = [exact_rel]

    # Pre-execution snapshot trigger (creates branch)
    supervisor_svc._capture_snapshot_if_needed(command, first_task)
    assert command.project_run_git_branch_created is True

    # Verify active branch in repo
    res_b = subprocess.run(["git", "branch", "--show-current"], cwd=str(temp_git_repo), capture_output=True, text=True)
    assert res_b.stdout.strip() == preview.git_branch_name

    # Write target file inside repo
    target_path = (temp_git_repo / exact_rel).resolve()
    target_path.write_text("def main(): print('updated')\n", encoding="utf-8")

    # Complete all tasks
    for task in command.tasks:
        task.status = "completed"

    command.status = "completed"
    supervisor_svc.git_run_manager.finalize_successful_run(command=command)
    assert command.status == "completed"
    assert command.project_run_git_commit_hash is not None

    # Verify commit in git log
    res_log = subprocess.run(["git", "log", "-1", "--oneline"], cwd=str(temp_git_repo), capture_output=True, text=True)
    assert "Prometheus run" in res_log.stdout


@pytest.mark.asyncio
async def test_failed_run_does_not_auto_commit(supervisor_svc, temp_git_repo, tmp_path):
    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()

    prev_req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview = await supervisor_svc.preview_project_run(prev_req)

    commit_req = ProjectRunCommitRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        preview_digest=preview.preview_digest,
        execution_mode="isolated_branch",
    )
    commit_res = await supervisor_svc.commit_project_run(commit_req)
    command = await supervisor_svc.store.get(commit_res.command_id)

    first_task = command.tasks[0]
    first_task.exact_files = ["app.py"]
    supervisor_svc._capture_snapshot_if_needed(command, first_task)

    # Fail the task
    first_task.status = "failed"
    command.status = "failed"

    assert command.status == "failed"
    assert command.project_run_git_commit_hash is None


def test_git_status_endpoint(supervisor_svc, temp_git_repo, tmp_path, monkeypatch):
    client = TestClient(app)
    app.state.supervisor = supervisor_svc

    rel_path = temp_git_repo.relative_to(tmp_path).as_posix()

    import asyncio
    prev_req = ProjectRunPreviewRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        execution_mode="isolated_branch",
    )
    preview = asyncio.run(supervisor_svc.preview_project_run(prev_req))

    commit_req = ProjectRunCommitRequest(
        goal="app.py dosyasında düzenleme yap ve pytest çalıştır",
        workspace_path=rel_path,
        preview_digest=preview.preview_digest,
        execution_mode="isolated_branch",
    )
    commit_res = asyncio.run(supervisor_svc.commit_project_run(commit_req))

    res = client.get(f"/v1/supervisor/commands/{commit_res.command_id}/git-status")
    assert res.status_code == 200
    data = res.json()
    assert data["execution_mode"] == "isolated_branch"
    assert data["is_repository"] is True
    assert data["base_branch"] == "main"
    assert data["run_branch"] == preview.git_branch_name
    assert data["branch_created"] is False
