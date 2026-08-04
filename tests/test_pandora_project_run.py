from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
import pytest

from app.core.config import Settings
from app.core.schemas import (
    ProjectRunCommitRequest,
    ProjectRunCommitResponse,
    ProjectRunPreviewRequest,
    ProjectRunPreviewResponse,
    ProjectRunPreviewTask,
    WorkspaceProjectGitStatus,
    WorkspaceProjectsResponse,
    WorkspaceProjectSummary,
)
from app.main import app
from app.security.csrf import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.security.pandora import (
    PANDORA_PAIRING_REQUIRED_DETAIL,
    PANDORA_PROJECT_RUN_BUSY_DETAIL,
    PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL,
    PANDORA_PROJECT_RUN_PREVIEW_REQUIRED_DETAIL,
    PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL,
    PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL,
    PANDORA_SESSION_COOKIE_NAME,
    PandoraProjectRunBusyError,
    PandoraProjectRunRateLimitError,
    PandoraSessionManager,
)
from app.supervisor.models import SupervisorCommand, SupervisorTask


_MISSING = object()
_REMOTE_TOKEN = "pandora-project-run-token-0123456789ab"


def _basic_header() -> str:
    encoded = base64.b64encode(
        f"prometheus:{_REMOTE_TOKEN}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


async def _remote_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app,
            client=("192.0.2.30", 50000),
        ),
        base_url="https://prometheus.internal",
        headers={"host": "prometheus.internal", **kwargs.pop("headers", {})},
        **kwargs,
    )


async def _pair(
    client: httpx.AsyncClient,
    manager: PandoraSessionManager,
    *,
    device_name: str = "Pandora phone",
) -> str:
    code = manager.issue_pairing_code()
    response = await client.post(
        "/v1/pandora/pair",
        headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
        json={"code": code, "device_name": device_name},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get(PANDORA_SESSION_COOKIE_NAME)
    assert token
    return token


@dataclass
class _FakeWorkspaceProjects:
    def list_projects(self) -> WorkspaceProjectsResponse:
        return WorkspaceProjectsResponse(
            workspace_root_name="secret-root",
            projects=[
                WorkspaceProjectSummary(
                    name="Prometheus",
                    workspace_path=".",
                    project_types=["python", "fastapi"],
                    manifests=["pyproject.toml"],
                    suggested_verifications=["python -m pytest"],
                    git=WorkspaceProjectGitStatus(
                        is_repository=True,
                        git_root="C:/Users/private/Prometheus",
                        branch="main",
                        dirty=True,
                        changed_file_count=2,
                    ),
                )
            ],
            total=1,
            scan_depth=2,
            truncated=False,
        )


@dataclass
class _FakeSupervisor:
    preview_requests: list[ProjectRunPreviewRequest] = field(default_factory=list)
    commit_requests: list[ProjectRunCommitRequest] = field(default_factory=list)
    command: SupervisorCommand | None = None

    async def preview_project_run(
        self,
        request: ProjectRunPreviewRequest,
    ) -> ProjectRunPreviewResponse:
        self.preview_requests.append(request)
        return ProjectRunPreviewResponse(
            goal=request.goal,
            workspace_path=request.workspace_path,
            tasks=[
                ProjectRunPreviewTask(
                    title="Pandora endpointini güncelle",
                    assigned_agent="backend",
                    exact_files=["app/main.py", "tests/test_pandora_project_run.py"],
                    verification="python -m pytest -q tests/test_pandora_project_run.py",
                    acceptance_criteria=["Focused test geçer"],
                )
            ],
            exact_files=["app/main.py", "tests/test_pandora_project_run.py"],
            verification_commands=[
                "python -m pytest -q tests/test_pandora_project_run.py"
            ],
            warnings=["internal planner warning must not be exposed"],
            requires_approval=True,
            model_calls=0,
            total_tokens=0,
            side_effect_free=True,
            preview_digest=(
                "sha256:1111111111111111111111111111111111111111111111111111111111111111"
            ),
        )

    async def commit_project_run(
        self,
        request: ProjectRunCommitRequest,
    ) -> ProjectRunCommitResponse:
        self.commit_requests.append(request)
        task = SupervisorTask(
            id="task_secret_001",
            title="Pandora endpointini güncelle",
            priority="zorunlu",
            assigned_agent="backend",
            evidence=[],
            acceptance_criteria=["Focused test geçer"],
            dependencies=[],
            dependency_reason="Bağımsız",
            parallelizable="evet",
            verification="python -m pytest -q tests/test_pandora_project_run.py",
            user_approval="gerekli",
            exact_files=["app/main.py", "tests/test_pandora_project_run.py"],
            status="awaiting_approval",
            approval_id="appr_secret_001",
            approval_state="pending",
        )
        self.command = SupervisorCommand(
            id="cmd_mobile_001",
            goal=request.goal,
            status="awaiting_approval",
            autonomy_mode=request.autonomy_mode,
            plan_text="internal plan text",
            tasks=[task],
            project_run_preview_digest=request.preview_digest,
            project_run_workspace_path=request.workspace_path,
        )
        return ProjectRunCommitResponse(
            command_id=self.command.id,
            status=self.command.status,
            goal=self.command.goal,
            workspace_path=request.workspace_path,
            preview_digest=request.preview_digest,
            task_ids=[task.id],
            approval_ids=[task.approval_id or ""],
            requires_approval=True,
            model_calls=0,
            total_tokens=0,
            execution_started=False,
            created=True,
        )

    async def get(self, command_id: str) -> SupervisorCommand:
        if self.command is None or self.command.id != command_id:
            raise KeyError(command_id)
        return self.command


@pytest.fixture
def pandora_project_run_state() -> Iterator[tuple[PandoraSessionManager, _FakeSupervisor]]:
    previous_settings = getattr(app.state, "settings", _MISSING)
    previous_manager = getattr(app.state, "pandora_sessions", _MISSING)
    previous_supervisor = getattr(app.state, "supervisor", _MISSING)
    previous_projects = getattr(app.state, "workspace_projects", _MISSING)
    manager = PandoraSessionManager()
    supervisor = _FakeSupervisor()
    app.state.settings = Settings(
        _env_file=None,
        http_remote_access_enabled=True,
        http_auth_token=_REMOTE_TOKEN,
    )
    app.state.pandora_sessions = manager
    app.state.supervisor = supervisor
    app.state.workspace_projects = _FakeWorkspaceProjects()
    try:
        yield manager, supervisor
    finally:
        for name, previous in (
            ("settings", previous_settings),
            ("pandora_sessions", previous_manager),
            ("supervisor", previous_supervisor),
            ("workspace_projects", previous_projects),
        ):
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)


def test_project_run_session_state_is_rate_limited_bound_and_revoked() -> None:
    now = [100.0]
    manager = PandoraSessionManager(
        clock=lambda: now[0],
        project_run_requests_per_window=1,
        project_run_rate_window_seconds=10,
        project_run_preview_ttl_seconds=5,
    )
    code = manager.issue_pairing_code()
    token = manager.create_session(code=code, device_name="Phone")

    assert manager.begin_project_run_request(token) is not None
    with pytest.raises(PandoraProjectRunBusyError, match=PANDORA_PROJECT_RUN_BUSY_DETAIL):
        manager.begin_project_run_request(token)
    manager.end_project_run_request(token)
    with pytest.raises(PandoraProjectRunRateLimitError, match=PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL):
        manager.begin_project_run_request(token)

    digest = "sha256:" + ("a" * 64)
    assert manager.remember_project_run_preview(
        token,
        preview_digest=digest,
        goal="Safe goal",
        workspace_path=".",
    )
    assert manager.project_run_preview_is_valid(
        token,
        preview_digest=digest,
        goal="Safe goal",
        workspace_path=".",
    )
    assert not manager.project_run_preview_is_valid(
        token,
        preview_digest=digest,
        goal="Changed goal",
        workspace_path=".",
    )
    assert manager.register_project_run(token, "cmd_mobile")
    assert manager.owns_project_run(token, "cmd_mobile")
    assert manager.latest_project_run_id(token) == "cmd_mobile"

    now[0] = 106.0
    assert not manager.project_run_preview_is_valid(
        token,
        preview_digest=digest,
        goal="Safe goal",
        workspace_path=".",
    )
    assert manager.revoke(token)
    assert not manager.owns_project_run(token, "cmd_mobile")


@pytest.mark.asyncio
async def test_project_run_routes_require_pandora_session_even_with_admin_credentials(
    pandora_project_run_state: tuple[PandoraSessionManager, _FakeSupervisor],
) -> None:
    async with await _remote_client(
        headers={"Authorization": _basic_header()}
    ) as client:
        projects = await client.get("/v1/pandora/projects")
        preview = await client.post(
            "/v1/pandora/project-run/preview",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"goal": "app/main.py güncelle", "workspace_path": "."},
        )

    assert projects.status_code == 401
    assert projects.json() == {"detail": PANDORA_PAIRING_REQUIRED_DETAIL}
    assert preview.status_code == 401
    assert preview.json() == {"detail": PANDORA_PAIRING_REQUIRED_DETAIL}


@pytest.mark.asyncio
async def test_projects_preview_commit_and_status_are_safe_and_narrow(
    pandora_project_run_state: tuple[PandoraSessionManager, _FakeSupervisor],
) -> None:
    manager, supervisor = pandora_project_run_state
    async with await _remote_client() as client:
        await _pair(client, manager)
        projects = await client.get("/v1/pandora/projects")
        preview = await client.post(
            "/v1/pandora/project-run/preview",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"goal": "app/main.py güncelle", "workspace_path": "."},
        )
        preview_data = preview.json()
        commit = await client.post(
            "/v1/pandora/project-run/commit",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={
                "goal": preview_data["goal"],
                "workspace_path": preview_data["workspace_path"],
                "preview_digest": preview_data["preview_digest"],
                "autonomy_mode": "trusted",
                "background": False,
                "force_new": True,
                "provider": "secret-provider",
            },
        )
        status = await client.get(
            f"/v1/pandora/project-run/{commit.json()['command_id']}"
        )
        latest = await client.get("/v1/pandora/project-run/latest")

    assert projects.status_code == 200
    assert projects.headers["cache-control"] == "no-store"
    assert projects.json() == {
        "projects": [
            {
                "name": "Prometheus",
                "workspace_path": ".",
                "project_types": ["python", "fastapi"],
                "dirty": True,
            }
        ],
        "truncated": False,
    }
    serialized_projects = projects.text.casefold()
    for forbidden in ("git_root", "c:/users", "secret-root", "branch"):
        assert forbidden not in serialized_projects

    assert preview.status_code == 200, preview.text
    assert preview.headers["cache-control"] == "no-store"
    assert preview_data["side_effect_free"] is True
    assert preview_data["requires_approval"] is True
    assert preview_data["task_count"] == 1
    assert preview_data["exact_file_count"] == 2
    assert preview_data["expires_in"] == manager.project_run_preview_ttl_seconds
    assert "assigned_agent" not in preview.text
    assert "warnings" not in preview_data
    assert "internal planner warning" not in preview.text
    assert len(supervisor.preview_requests) == 1

    assert commit.status_code == 200, commit.text
    assert commit.headers["cache-control"] == "no-store"
    assert commit.json() == {
        "command_id": "cmd_mobile_001",
        "status": "awaiting_approval",
        "goal": "app/main.py güncelle",
        "workspace_path": ".",
        "task_count": 1,
        "requires_desktop_approval": True,
        "execution_started": False,
        "created": True,
    }
    committed_request = supervisor.commit_requests[0]
    assert committed_request.autonomy_mode == "locked"
    assert committed_request.background is True
    assert committed_request.force_new is False
    assert "approval_ids" not in commit.text
    assert "task_secret" not in commit.text
    assert "appr_secret" not in commit.text

    assert status.status_code == 200, status.text
    assert latest.status_code == 200, latest.text
    assert latest.json() == status.json()
    status_data = status.json()
    assert status_data["command_id"] == "cmd_mobile_001"
    assert status_data["requires_desktop_approval"] is True
    assert status_data["waiting_approval_tasks"] == 1
    assert status_data["progress_percent"] == 0
    assert status_data["tasks"] == [
        {
            "title": "Pandora endpointini güncelle",
            "status": "awaiting_approval",
            "approval_state": "pending",
            "exact_file_count": 2,
        }
    ]
    for forbidden in (
        "approval_id",
        "task_secret",
        "appr_secret",
        "plan_text",
        "assigned_agent",
        "verification",
    ):
        assert forbidden not in status.text


@pytest.mark.asyncio
async def test_commit_requires_same_session_preview_and_status_is_owner_scoped(
    pandora_project_run_state: tuple[PandoraSessionManager, _FakeSupervisor],
) -> None:
    manager, _supervisor = pandora_project_run_state
    async with await _remote_client() as first:
        await _pair(first, manager, device_name="First")
        preview = await first.post(
            "/v1/pandora/project-run/preview",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"goal": "app/main.py güncelle", "workspace_path": "."},
        )
        preview_data = preview.json()
        commit = await first.post(
            "/v1/pandora/project-run/commit",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={
                "goal": preview_data["goal"],
                "workspace_path": preview_data["workspace_path"],
                "preview_digest": preview_data["preview_digest"],
            },
        )

    async with await _remote_client() as second:
        await _pair(second, manager, device_name="Second")
        foreign_commit = await second.post(
            "/v1/pandora/project-run/commit",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={
                "goal": preview_data["goal"],
                "workspace_path": preview_data["workspace_path"],
                "preview_digest": preview_data["preview_digest"],
            },
        )
        foreign_status = await second.get(
            f"/v1/pandora/project-run/{commit.json()['command_id']}"
        )
        foreign_latest = await second.get("/v1/pandora/project-run/latest")

    assert foreign_commit.status_code == 409
    assert foreign_commit.json() == {
        "detail": PANDORA_PROJECT_RUN_PREVIEW_REQUIRED_DETAIL
    }
    assert foreign_status.status_code == 404
    assert foreign_status.json() == {
        "detail": PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL
    }
    assert foreign_latest.status_code == 404
    assert foreign_latest.json() == {
        "detail": PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL
    }


@pytest.mark.asyncio
async def test_project_run_validation_and_internal_errors_are_sanitized(
    pandora_project_run_state: tuple[PandoraSessionManager, _FakeSupervisor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, supervisor = pandora_project_run_state
    async with await _remote_client() as client:
        await _pair(client, manager)
        invalid_path = await client.post(
            "/v1/pandora/project-run/preview",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"goal": "app/main.py güncelle", "workspace_path": "../../secret"},
        )

        async def explode(_request: ProjectRunPreviewRequest) -> ProjectRunPreviewResponse:
            raise RuntimeError("C:/Users/private secret provider route")

        monkeypatch.setattr(supervisor, "preview_project_run", explode)
        unavailable = await client.post(
            "/v1/pandora/project-run/preview",
            headers={CSRF_HEADER_NAME: CSRF_HEADER_VALUE},
            json={"goal": "app/main.py güncelle", "workspace_path": "."},
        )

    assert invalid_path.status_code == 422
    assert supervisor.preview_requests == []
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL}
    serialized = unavailable.text.casefold()
    for forbidden in ("c:/users", "private", "provider", "route"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_project_run_mutations_require_csrf(
    pandora_project_run_state: tuple[PandoraSessionManager, _FakeSupervisor],
) -> None:
    manager, _supervisor = pandora_project_run_state
    async with await _remote_client() as client:
        await _pair(client, manager)
        preview = await client.post(
            "/v1/pandora/project-run/preview",
            json={"goal": "app/main.py güncelle", "workspace_path": "."},
        )

    assert preview.status_code == 403
