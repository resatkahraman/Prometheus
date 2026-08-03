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
        yield c


def test_project_run_preview_is_side_effect_free_and_zero_model(client, monkeypatch):
    # Fail-loud monkeypatch to guarantee zero model/provider calls
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
                exact_files=[],  # Empty exact_files
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
                verification="   ",  # Blank verification
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
