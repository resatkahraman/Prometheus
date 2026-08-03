from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.planning.models import PlanEvidence, PlanTask, PlanningDocument


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.headers["X-Requested-With"] = "XMLHttpRequest"
        c.headers["X-Prometheus-CSRF"] = "1"
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


def test_project_run_preview_is_side_effect_free_and_zero_model(client, monkeypatch):
    def fail_on_model_call(*args, **kwargs):
        raise AssertionError("project run preview must not call a model")

    monkeypatch.setattr(
        "app.supervisor.service.SupervisorService._plan",
        fail_on_model_call,
    )
    monkeypatch.setattr(
        "app.orchestration.orchestrator.Orchestrator.run",
        fail_on_model_call,
    )

    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "app/main.py dosyasında düzenleme yap ve pytest çalıştır", "workspace_path": "."},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["model_calls"] == 0
    assert data["total_tokens"] == 0
    assert data["side_effect_free"] is True
    assert data["requires_approval"] is True
    assert data["preview_digest"].startswith("sha256:")
    assert isinstance(data["tasks"], list)
    assert len(data["tasks"]) > 0


def test_project_run_preview_returns_exact_scope_and_verifications(client):
    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "app/main.py dosyasında düzenleme yap ve pytest çalıştır", "workspace_path": "."},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "exact_files" in data
    assert "verification_commands" in data
    assert isinstance(data["exact_files"], list)
    assert isinstance(data["verification_commands"], list)
    assert len(data["exact_files"]) > 0
    assert len(data["verification_commands"]) > 0


def test_project_run_preview_rejects_workspace_escape(client):
    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "app/main.py düzenle", "workspace_path": "../../secret"},
    )
    assert response.status_code == 422


def test_project_run_preview_rejects_plan_without_exact_files(client, monkeypatch):
    bad_doc = PlanningDocument(
        verified_facts=["Proje yapısı mevcut."],
        tasks=[
            PlanTask(
                id="TASK-001",
                title="Bozuk görev",
                priority="zorunlu",
                assigned_agent="backend",
                evidence=[PlanEvidence(type="user_request", value="Bozuk istek")],
                acceptance_criteria=["Kriter"],
                dependencies=[],
                dependency_reason="Yok",
                parallelizable="evet",
                verification="pytest",
                user_approval="gerekmez",
                exact_files=[],
            )
        ]
    )

    async def mock_kernel_build(*args, **kwargs):
        from dataclasses import dataclass

        @dataclass
        class MockResult:
            document = bad_doc
            text = "Mock text"
            tools_used = []
            project_types = []

        return MockResult()

    monkeypatch.setattr(app.state.supervisor.planning_kernel, "build", mock_kernel_build)

    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "Bozuk görev testi", "workspace_path": "."},
    )
    assert response.status_code == 422
    assert "exact file" in response.json()["detail"].lower()


def test_project_run_preview_rejects_plan_without_verification(client, monkeypatch):
    bad_doc = PlanningDocument(
        verified_facts=["Proje yapısı mevcut."],
        tasks=[
            PlanTask(
                id="TASK-001",
                title="Doğrulamasız görev",
                priority="zorunlu",
                assigned_agent="backend",
                evidence=[PlanEvidence(type="file", value="app/main.py")],
                acceptance_criteria=["Kriter"],
                dependencies=[],
                dependency_reason="Yok",
                parallelizable="evet",
                verification="   ",
                user_approval="gerekmez",
                exact_files=["app/main.py"],
            )
        ]
    )

    async def mock_kernel_build(*args, **kwargs):
        from dataclasses import dataclass

        @dataclass
        class MockResult:
            document = bad_doc
            text = "Mock text"
            tools_used = []
            project_types = []

        return MockResult()

    monkeypatch.setattr(app.state.supervisor.planning_kernel, "build", mock_kernel_build)

    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "Doğrulamasız görev testi", "workspace_path": "."},
    )
    assert response.status_code == 422
    assert "doğrulama" in response.json()["detail"].lower()


def test_project_run_preview_does_not_persist_command_or_emit_event(client, monkeypatch):
    saved_commands = []
    events_emitted = []

    async def fail_save_command(*args, **kwargs):
        saved_commands.append(args)

    monkeypatch.setattr(app.state.supervisor.store, "put", fail_save_command)

    def spy_emit_event(*args, **kwargs):
        events_emitted.append(args)

    monkeypatch.setattr(app.state.supervisor, "_event", spy_emit_event)

    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "app/main.py dosyasında düzenleme yap ve pytest çalıştır", "workspace_path": "."},
    )
    assert response.status_code == 200, response.text
    assert len(saved_commands) == 0
    assert len(events_emitted) == 0


def test_project_run_preview_does_not_record_usage(client, monkeypatch):
    route_calls = []

    async def spy_record_route_call(*args, **kwargs):
        route_calls.append(args)

    monkeypatch.setattr(app.state.store, "record_route_call", spy_record_route_call)

    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "app/main.py dosyasında düzenleme yap ve pytest çalıştır", "workspace_path": "."},
    )
    assert response.status_code == 200, response.text
    assert len(route_calls) == 0


def test_project_run_preview_response_does_not_expose_absolute_workspace_path(client):
    response = client.post(
        "/v1/supervisor/project-run/preview",
        json={"goal": "app/main.py dosyasında düzenleme yap ve pytest çalıştır", "workspace_path": "."},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert not Path(data["workspace_path"]).is_absolute()
    for f in data["exact_files"]:
        assert not Path(f).is_absolute()
        assert ".." not in f


def test_project_run_preview_digest_is_stable_and_changes_with_scope(client):
    goal1 = "app/main.py dosyasında düzenleme yap ve pytest çalıştır"
    res1 = client.post("/v1/supervisor/project-run/preview", json={"goal": goal1, "workspace_path": "."})
    assert res1.status_code == 200
    digest1 = res1.json()["preview_digest"]

    res1_again = client.post("/v1/supervisor/project-run/preview", json={"goal": goal1, "workspace_path": "."})
    assert res1_again.json()["preview_digest"] == digest1

    goal2 = "app/core/schemas.py dosyasında düzenleme yap ve pytest çalıştır"
    res2 = client.post("/v1/supervisor/project-run/preview", json={"goal": goal2, "workspace_path": "."})
    assert res2.status_code == 200
    digest2 = res2.json()["preview_digest"]
    assert digest1 != digest2


def test_project_run_commit_creates_command_without_executing_or_calling_model(client, monkeypatch):
    def fail_on_execution(*args, **kwargs):
        raise AssertionError("Commit must not execute or call model/provider")

    monkeypatch.setattr("app.supervisor.service.SupervisorService._plan", fail_on_execution)
    monkeypatch.setattr("app.orchestration.orchestrator.Orchestrator.run", fail_on_execution)

    goal = "app/main.py dosyasında benzersiz commit oluşturma testi 1"
    preview_res = client.post("/v1/supervisor/project-run/preview", json={"goal": goal, "workspace_path": "."})
    assert preview_res.status_code == 200
    preview_digest = preview_res.json()["preview_digest"]

    commit_res = client.post(
        "/v1/supervisor/project-run/commit",
        json={
            "goal": goal,
            "workspace_path": ".",
            "preview_digest": preview_digest,
            "autonomy_mode": "task",
            "background": True,
            "force_new": False,
        },
    )
    assert commit_res.status_code == 200, commit_res.text
    commit_data = commit_res.json()

    assert commit_data["created"] is True
    assert commit_data["execution_started"] is False
    assert commit_data["model_calls"] == 0
    assert commit_data["total_tokens"] == 0
    assert commit_data["requires_approval"] is True
    assert commit_data["command_id"].startswith("cmd_")
    assert len(commit_data["task_ids"]) > 0
    assert len(commit_data["approval_ids"]) > 0


def test_project_run_commit_rejects_stale_preview_digest(client):
    goal = "app/main.py dosyasında düzenleme yap ve pytest çalıştır"
    fake_digest = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

    commit_res = client.post(
        "/v1/supervisor/project-run/commit",
        json={
            "goal": goal,
            "workspace_path": ".",
            "preview_digest": fake_digest,
            "autonomy_mode": "task",
            "background": True,
            "force_new": False,
        },
    )
    assert commit_res.status_code == 409
    assert "stale" in commit_res.json()["detail"].lower()


def test_project_run_commit_is_idempotent(client):
    goal = "app/main.py dosyasında benzersiz idempotent test hedefi"
    preview_res = client.post("/v1/supervisor/project-run/preview", json={"goal": goal, "workspace_path": "."})
    preview_digest = preview_res.json()["preview_digest"]

    commit_payload = {
        "goal": goal,
        "workspace_path": ".",
        "preview_digest": preview_digest,
        "autonomy_mode": "task",
        "background": True,
        "force_new": False,
    }

    res1 = client.post("/v1/supervisor/project-run/commit", json=commit_payload)
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert data1["created"] is True

    res2 = client.post("/v1/supervisor/project-run/commit", json=commit_payload)
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2["created"] is False
    assert data2["command_id"] == data1["command_id"]
    assert data2["task_ids"] == data1["task_ids"]


def test_project_run_commit_rejects_when_active_command_exists(client, monkeypatch):
    async def mock_active_command(self):
        from app.supervisor.models import SupervisorCommand
        return SupervisorCommand(
            id="cmd_active_existing",
            goal="Aktif komut",
            status="running",
            plan_text="Plan",
            tasks=[],
        )

    monkeypatch.setattr("app.supervisor.service.SupervisorService._active_command", mock_active_command)

    goal = "app/main.py dosyasında benzersiz active command guard hedefi"
    p = client.post("/v1/supervisor/project-run/preview", json={"goal": goal, "workspace_path": "."}).json()
    c = client.post(
        "/v1/supervisor/project-run/commit",
        json={"goal": goal, "workspace_path": ".", "preview_digest": p["preview_digest"]},
    )
    assert c.status_code == 409
    assert "aktif bir görev" in c.json()["detail"].lower()
