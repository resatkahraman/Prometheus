import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workspace.projects import WorkspaceProjectManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir(parents=True, exist_ok=True)

    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    mgr = WorkspaceProjectManager(workspace_root=ws_root, state_root=state_root)

    with TestClient(app) as c:
        c.headers["X-Requested-With"] = "XMLHttpRequest"
        c.headers["X-Prometheus-CSRF"] = "1"
        monkeypatch.setattr(app.state, "workspace_projects", mgr)
        yield c


def test_workspace_root_candidate_and_project_types(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir(parents=True, exist_ok=True)

    (ws_root / "pyproject.toml").write_text('[project]\nname="test"\ndependencies=["fastapi"]', encoding="utf-8")
    (ws_root / "app").mkdir()
    (ws_root / "app" / "main.py").write_text("from fastapi import FastAPI", encoding="utf-8")

    mgr = WorkspaceProjectManager(workspace_root=ws_root, state_root=tmp_path / "state")
    res = mgr.list_projects()

    assert res.total >= 1
    root_proj = next((p for p in res.projects if p.workspace_path == "."), None)
    assert root_proj is not None
    assert "python" in root_proj.project_types
    assert "fastapi" in root_proj.project_types


def test_nested_depth_scanning_and_ignored_directories(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    # Depth 1 project
    proj1 = ws_root / "proj1"
    proj1.mkdir()
    (proj1 / "package.json").write_text('{"dependencies": {"react": "^18.0.0", "typescript": "^5.0.0"}}', encoding="utf-8")

    # Depth 2 project
    group = ws_root / "group"
    group.mkdir()
    proj2 = group / "proj2"
    proj2.mkdir()
    (proj2 / "Cargo.toml").write_text('[package]\nname="proj2"', encoding="utf-8")

    # Depth 3 project (should be ignored by depth limit 2)
    subgroup = proj2 / "subgroup"
    subgroup.mkdir()
    proj3 = subgroup / "proj3"
    proj3.mkdir()
    (proj3 / "go.mod").write_text("module proj3", encoding="utf-8")

    # Ignored directories
    node_modules = proj1 / "node_modules"
    node_modules.mkdir()
    (node_modules / "package.json").write_text("{}", encoding="utf-8")

    pytest_tmp = ws_root / ".pytest_tmp_dir"
    pytest_tmp.mkdir()
    (pytest_tmp / "pyproject.toml").write_text("", encoding="utf-8")

    mgr = WorkspaceProjectManager(workspace_root=ws_root, state_root=tmp_path / "state", scan_depth=2)
    res = mgr.list_projects()

    paths = [p.workspace_path for p in res.projects]
    assert "proj1" in paths
    assert "group/proj2" in paths
    assert "group/proj2/subgroup/proj3" not in paths
    assert "proj1/node_modules" not in paths
    assert ".pytest_tmp_dir" not in paths

    proj1_summary = next(p for p in res.projects if p.workspace_path == "proj1")
    assert "node" in proj1_summary.project_types
    assert "react" in proj1_summary.project_types
    assert "typescript" in proj1_summary.project_types


def test_root_escape_and_sensitive_paths_blocked(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    mgr = WorkspaceProjectManager(workspace_root=ws_root, state_root=tmp_path / "state")

    with pytest.raises(ValueError, match="Geçersiz veya engellenmiş"):
        mgr.select_project("../../secret")

    with pytest.raises(ValueError, match="Geçersiz veya engellenmiş"):
        mgr.select_project(".env")


def test_verification_suggestions_from_manifests_without_making_up_scripts(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    proj = ws_root / "my_node_app"
    proj.mkdir()
    (proj / "package.json").write_text(json.dumps({
        "name": "my_node_app",
        "scripts": {
            "test": "jest",
            "build": "tsc"
        }
    }), encoding="utf-8")
    (proj / "yarn.lock").write_text("", encoding="utf-8")

    mgr = WorkspaceProjectManager(workspace_root=ws_root, state_root=tmp_path / "state")
    res = mgr.select_project("my_node_app")

    verifs = res.project.suggested_verifications
    assert "yarn test" in verifs
    assert "yarn run build" in verifs
    assert "yarn run lint" not in verifs  # Not in scripts, must not be invented


def test_project_select_updates_recent_state(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    p1 = ws_root / "p1"
    p1.mkdir()
    (p1 / "requirements.txt").write_text("", encoding="utf-8")

    p2 = ws_root / "p2"
    p2.mkdir()
    (p2 / "requirements.txt").write_text("", encoding="utf-8")

    mgr = WorkspaceProjectManager(workspace_root=ws_root, state_root=tmp_path / "state")

    mgr.select_project("p1")
    mgr.select_project("p2")

    projects = mgr.list_projects().projects
    p2_sum = next(p for p in projects if p.workspace_path == "p2")
    p1_sum = next(p for p in projects if p.workspace_path == "p1")

    assert p2_sum.recent_rank == 1
    assert p1_sum.recent_rank == 2


def test_http_list_projects_endpoint(client):
    res = client.get("/v1/workspace/projects")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "workspace_root_name" in data
    assert "projects" in data
    assert isinstance(data["projects"], list)


def test_http_select_project_endpoint(client):
    res = client.post("/v1/workspace/projects/select", json={"workspace_path": "."})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["selected"] is True
    assert data["project"]["workspace_path"] == "."


def test_http_select_project_rejects_invalid_path(client):
    res = client.post("/v1/workspace/projects/select", json={"workspace_path": "../../invalid"})
    assert res.status_code == 422
