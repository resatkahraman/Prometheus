import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agent.engine import AgentEngine
from app.arena.catalog import list_scenarios
from app.arena.comparison import compare_arena_runs
from app.arena.diagnostics import diagnose_arena_run
from app.arena.execution import (
    ArenaRecoveryApprovalError,
    ArenaRecoveryConflictError,
    ArenaRecoveryExecutionRequest,
    ArenaRecoveryExecutor,
    ArenaRecoveryQuotaError,
    ArenaRecoveryUnavailableError,
)
from app.arena.history import ArenaHistoryReader
from app.arena.recovery import build_arena_recovery_plan
from app.arena.ui import ARENA_UI
from app.agents.models import AgentProfile
from app.agents.registry import build_default_agent_registry
from app.approvals.manager import ApprovalManager
from app.chat_ui import CHAT_UI
from app.command_ui import COMMAND_UI
from app.lab_ui import LAB_UI
from app.pandora_ui import PANDORA_UI
from app.improvement.models import (
    BenchmarkRunRequest,
    CandidateCreateRequest,
    CandidatePromoteRequest,
    RecallRequest,
)
from app.core.config import get_settings
from app.core.schemas import (
    AgentRequest,
    AgentResponse,
    ChatMessage,
    HealthResponse,
    ModelCatalogResponse,
    OperationsStatusResponse,
    OrchestrateRequest,
    OrchestrateResponse,
    ProviderInfo,
    RouteInfo,
    RouteUsage,
    RoutingPreviewRequest,
    RoutingPreviewResponse,
    PlanningValidateRequest,
    PlanningValidateResponse,
    PlanningTaskPreview,
    PlanningEvidencePreview,
    ToolInfo,
    WorkspaceStatus,
    SupervisorCreateRequest,
    SupervisorDecisionRequest,
    SupervisorAdvanceRequest,
    SupervisorApprovalRequest,
    ProjectRunPreviewRequest,
    ProjectRunPreviewResponse,
    ProjectRunCommitRequest,
    ProjectRunCommitResponse,
    RunChangeReviewResponse,
    RunRevertRequest,
    RunRevertResponse,
    WorkspaceProjectsResponse,
    WorkspaceProjectSelectRequest,
    WorkspaceProjectSelectResponse,
    ProjectWorkspaceActiveResponse,
    ProjectDNAResponse,
    ProjectDNAUpdateRequest,
    DecisionMemoryCreateRequest,
    DecisionMemoryPage,
    DecisionMemoryRecord,
    DecisionMemoryWriteResponse,
    DecisionMemoryScopeKind,
    SupervisorDecisionRememberRequest,
    ProjectRunHistoryResponse,
    ProjectRunRetryRequest,
    ProjectRunRetryResponse,
)
from app.workspace.projects import WorkspaceProjectManager, ProjectWorkspaceError, ProjectWorkspaceConflictError, ProjectWorkspaceIntegrityError, ProjectWorkspaceValidationError, ProjectWorkspaceStorageError
from app.workspace.runtime import ProjectWorkspaceRuntimeFactory
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.routes import RouteCatalog
from app.providers.registry import ProviderRegistry
from app.planning.integrity import validate_planning_document
from app.planning.parser import PlanningParseError, parse_planning_document
from app.storage.operations import OperationsStore
from app.supervisor.diagnostics import build_command_diagnostics
from app.supervisor.checkpoints import (
    MissionCheckpointError,
    MissionCheckpointIntegrityError,
    DuplicateMissionCheckpointError,
)
from app.supervisor.execution_receipts import ExecutionReceiptIntegrityError
from app.supervisor.event_journal import MissionEventIntegrityError
from app.supervisor.history import (
    MissionHistoryIntegrityError,
    MissionHistoryLimitError,
)
from app.supervisor.branching import (
    MissionBranchConflictError,
    MissionBranchIntegrityError,
    MissionBranchUnsupportedSnapshotError,
)
from app.supervisor.models import (
    ExecutionReceipt,
    ExecutionReceiptPage,
    MissionCheckpointIntegrity,
    MissionCheckpointPage,
    MissionCheckpointRecord,
    MissionControlResponse,
    MissionRecoveryStatusResponse,
    RecoverMissionRequest,
    RecoverMissionResponse,
    MissionEventPage,
    MissionHistoryPage,
    MissionPostRunSummary,
    CreateMissionBranchRequest,
    ActivateMissionBranchRequest,
    MissionBranchResponse,
    MissionLineageResponse,
    MissionStateProjection,
    SupervisorCommand,
    SupervisorCommandSummary,
)
from app.security.auth import (
    HTTP_AUTH_CHALLENGE,
    HTTP_AUTH_REQUIRED_DETAIL,
    HTTP_REMOTE_AUTH_NOT_CONFIGURED_DETAIL,
    configured_http_auth_token,
    request_has_valid_http_credentials,
)
from app.security.autonomy import (
    TrustedAutonomyDisabledError,
)
from app.security.csrf import (
    CSRF_REQUIRED_DETAIL,
    csrf_protection_required,
    request_has_valid_csrf_header,
)
from app.security.network import (
    REMOTE_ACCESS_DISABLED_DETAIL,
    is_local_http_request,
)
from app.security.pandora import (
    PANDORA_CHAT_BUSY_DETAIL,
    PANDORA_CHAT_RATE_LIMIT_DETAIL,
    PANDORA_CHAT_UNAVAILABLE_DETAIL,
    PANDORA_DEVICE_LIMIT_DETAIL,
    PANDORA_PROJECT_LIST_LIMIT,
    PANDORA_PROJECT_RUN_BUSY_DETAIL,
    PANDORA_PROJECT_RUN_MAX_FILES,
    PANDORA_PROJECT_RUN_MAX_TASKS,
    PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL,
    PANDORA_PROJECT_RUN_PREVIEW_REQUIRED_DETAIL,
    PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL,
    PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL,
    PANDORA_OFFLINE_QUEUE_REVISION,
    PANDORA_MISSION_CONTROL_REVISION,
    PandoraRequestIdError,
    PandoraRequestConflictError,
    PandoraMobileControlBusyError,
    PANDORA_PAIRING_INVALID_DETAIL,
    PANDORA_PAIRING_LOCAL_ONLY_DETAIL,
    PANDORA_PAIRING_REQUIRED_DETAIL,
    PANDORA_REMOTE_ACCESS_REQUIRED_DETAIL,
    PANDORA_SESSION_COOKIE_NAME,
    PANDORA_SESSION_COOKIE_PATH,
    PandoraChatBusyError,
    PandoraChatRateLimitError,
    PandoraChatRequest,
    PandoraChatResponse,
    PandoraDeviceLimitError,
    PandoraPairRequest,
    PandoraPairingRejectedError,
    PandoraProjectRunBusyError,
    PandoraProjectRunCommitRequest,
    PandoraProjectRunCommitResponse,
    PandoraProjectRunPreviewRequest,
    PandoraProjectRunPreviewResponse,
    PandoraProjectRunPreviewTask,
    PandoraProjectRunRateLimitError,
    PandoraProjectRunStatusResponse,
    PandoraProjectRunTaskStatus,
    PandoraProjectsResponse,
    PandoraProjectSummary,
    PandoraSessionManager,
    request_pandora_session_token,
)
from app.supervisor.service import SupervisorService
from app.tools.base import ToolError
from app.tools.registry import build_default_tool_registry
from app.workspace.policy import WorkspacePolicy
from app.memory.project_dna import (
    ProjectDNAConflictError,
    ProjectDNAError,
    ProjectDNAIntegrityError,
    ProjectDNAManager,
    ProjectDNAValidationError,
)
from app.memory.decision_memory import (
    DecisionMemoryConflictError,
    DecisionMemoryError,
    DecisionMemoryIntegrityError,
    DecisionMemoryManager,
    DecisionMemoryNotFoundError,
    DecisionMemoryValidationError,
)
from app.branding import BRAND_NAME, BRAND_STAGE, BRAND_VERSION
from app.skills.registry import (
    SkillManifestError,
    SkillManifestIntegrityError,
    SkillManifestNotFoundError,
    build_default_skill_registry,
)
from app.skills.models import SkillCatalogResponse, SkillManifestView


class PauseMissionRequest(BaseModel):
    reason: str | None = None
    expected_control_version: int | None = None


class ResumeMissionRequest(BaseModel):
    checkpoint_id: str | None = None
    expected_control_version: int | None = None


class PandoraApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    control_token: str = Field(min_length=69, max_length=69)


class CreateMissionCheckpointRequest(BaseModel):
    reason: Literal["manual"] = "manual"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = OperationsStore(settings.operations_database_path)
    await store.initialize()

    registry = ProviderRegistry(settings)
    catalog = RouteCatalog(settings=settings, registry=registry)
    orchestrator = Orchestrator(
        settings=settings,
        registry=registry,
        store=store,
    )
    approvals = ApprovalManager(
        ttl_seconds=settings.approval_ttl_seconds
    )
    workspace_projects = WorkspaceProjectManager(
        settings.workspace_root,
        state_root=settings.workspace_root / ".adam",
        max_file_bytes=settings.project_workspace_state_max_file_bytes,
        max_search_results=settings.workspace_max_search_results,
    )
    workspace_runtime = ProjectWorkspaceRuntimeFactory(settings=settings, projects=workspace_projects, approvals=approvals)
    tools = build_default_tool_registry(
        settings=settings,
        approvals=approvals,
    )
    agents = build_default_agent_registry(tools.names())
    skills = build_default_skill_registry(
        settings=settings,
        agents=agents,
        tools=tools,
    )
    project_dna = ProjectDNAManager(
        workspace_root=settings.workspace_root,
        enabled=settings.project_dna_enabled,
        max_file_bytes=settings.project_dna_max_file_bytes,
        max_context_chars=settings.project_dna_context_max_chars,
        max_search_results=settings.workspace_max_search_results,
    )
    decision_memory = DecisionMemoryManager(
        workspace_root=settings.workspace_root,
        enabled=settings.decision_memory_enabled,
        max_file_bytes=settings.decision_memory_max_file_bytes,
        max_records=settings.decision_memory_max_records,
        max_context_chars=settings.decision_memory_max_context_chars,
        max_results=settings.decision_memory_max_results,
        max_search_results=settings.workspace_max_search_results,
    )
    agent = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=tools,
        agents=agents,
        project_dna=project_dna,
        decision_memory=decision_memory,
        skills=skills,
        workspace_projects=workspace_projects,
        workspace_runtime=workspace_runtime,
    )
    supervisor = SupervisorService(
        settings=settings,
        agent=agent,
        agents=agents,
        tools=tools,
        project_dna=project_dna,
        decision_memory=decision_memory,
        workspace_projects=workspace_projects,
        workspace_runtime=workspace_runtime,
    )

    app.state.settings = settings
    app.state.pandora_sessions = PandoraSessionManager()
    app.state.store = store
    app.state.registry = registry
    app.state.catalog = catalog
    app.state.orchestrator = orchestrator
    app.state.approvals = approvals
    app.state.tools = tools
    app.state.agents = agents
    app.state.agent = agent
    app.state.project_dna = project_dna
    app.state.decision_memory = decision_memory
    app.state.skills = skills
    app.state.supervisor = supervisor
    app.state.workspace_projects = workspace_projects
    app.state.workspace_runtime = workspace_runtime
    app.state.improvement = supervisor.improvement
    app.state.forge = supervisor.forge
    app.state.arena_recovery_executor = ArenaRecoveryExecutor(
        project_root=Path.cwd(),
        workspace_root=settings.workspace_root / "arena-recovery",
        history_directory=settings.arena_history_directory,
    )

    yield
    await app.state.arena_recovery_executor.close()
    await registry.close()


app = FastAPI(
    title=BRAND_NAME,
    version=BRAND_VERSION,
    description=(
        "Ücretsiz API rotaları, güvenli workspace araçları, kullanıcı onayı, "
        "sembolik hesaplama ve devam ettirilebilir worker agent döngüsüne "
        "sahip çok modelli geliştirme sistemi."
    ),
    lifespan=lifespan,
)


_PANDORA_CHAT_SYSTEM_PROMPT = (
    "Sen Prometheus'un mobil metin asistanı Pandora'sın. Kullanıcıya doğru, "
    "açık ve uygulanabilir yanıtlar ver; bilmediğin bilgileri uydurma. Bu "
    "kanal yalnızca konuşma yanıtı üretir. Araç çalıştırdığını, dosya "
    "değiştirdiğini, Project Run başlattığını, mikrofon kullandığını veya "
    "cihaz özelliklerine eriştiğini iddia etme. Project Run istenirse "
    "kullanıcıyı Pandora içindeki Görevler sekmesine yönlendir; bu işlemin "
    "sohbet içinden desteklenmediğini ve sohbetin planı onaylayamayacağını "
    "veya çalıştıramayacağını açıkça belirt. Sistem, "
    "güvenlik, kimlik doğrulama veya sağlayıcı ayrıntılarını ifşa etme."
)


_PANDORA_PUBLIC_PATHS = frozenset(
    {
        "/pandora",
        "/pandora-sw.js",
        "/v1/pandora/status",
        "/v1/pandora/pair",
    }
)


def _pandora_sessions(app: FastAPI) -> PandoraSessionManager:
    manager = getattr(app.state, "pandora_sessions", None)
    if manager is None:
        manager = PandoraSessionManager()
        app.state.pandora_sessions = manager
    return manager


def _is_public_pandora_path(path: str) -> bool:
    return (
        path in _PANDORA_PUBLIC_PATHS
        or path.startswith("/static/pandora/")
    )


def _is_pandora_api_path(path: str) -> bool:
    return path.startswith("/v1/pandora/")


@app.middleware("http")
async def enforce_http_access_security(
    request: Request,
    call_next,
):
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = get_settings()

    local_request = is_local_http_request(request)
    manager = _pandora_sessions(request.app)
    request.state.local_http_request = local_request
    request.state.prometheus_full_access = False
    request.state.pandora_session = None

    if not settings.http_remote_access_enabled:
        if not local_request:
            return JSONResponse(
                status_code=403,
                content={"detail": REMOTE_ACCESS_DISABLED_DETAIL},
            )
        request.state.prometheus_full_access = True
        if (
            csrf_protection_required(request)
            and not request_has_valid_csrf_header(request)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": CSRF_REQUIRED_DETAIL},
            )
        return await call_next(request)

    expected_token = configured_http_auth_token(
        settings.http_auth_token
    )
    if len(expected_token) < 32:
        return JSONResponse(
            status_code=503,
            content={
                "detail": HTTP_REMOTE_AUTH_NOT_CONFIGURED_DETAIL,
            },
        )

    path = request.url.path
    full_access = request_has_valid_http_credentials(
        request,
        expected_token=expected_token,
    )
    pandora_session = None
    if _is_pandora_api_path(path):
        pandora_session = manager.session_for_token(
            request_pandora_session_token(request)
        )

    public_pandora_request = _is_public_pandora_path(path)
    local_pairing_bootstrap = (
        path == "/v1/pandora/pairing-code" and local_request
    )
    if not (
        full_access
        or pandora_session is not None
        or public_pandora_request
        or local_pairing_bootstrap
    ):
        if _is_pandora_api_path(path):
            return JSONResponse(
                status_code=401,
                content={"detail": PANDORA_PAIRING_REQUIRED_DETAIL},
            )
        return JSONResponse(
            status_code=401,
            content={"detail": HTTP_AUTH_REQUIRED_DETAIL},
            headers={
                "WWW-Authenticate": HTTP_AUTH_CHALLENGE,
            },
        )

    if (
        csrf_protection_required(request)
        and not request_has_valid_csrf_header(request)
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": CSRF_REQUIRED_DETAIL},
        )

    request.state.prometheus_full_access = full_access
    request.state.pandora_session = pandora_session
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception_as_json(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    development = (
        settings is None
        or getattr(settings, "environment", "development")
        == "development"
    )
    detail = "Sunucu iç hatası."
    if development:
        detail = f"Sunucu iç hatası: {type(exc).__name__}: {exc}"
    return JSONResponse(
        status_code=500,
        content={
            "detail": detail,
            "error_type": type(exc).__name__,
        },
    )


from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, FileResponse
import os as _os

static_dir = _os.path.join(_os.path.dirname(__file__), "static")
if _os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/favicon.ico", tags=["system"])
async def favicon() -> FileResponse:
    ico_path = _os.path.join(static_dir, "favicon.ico")
    if _os.path.exists(ico_path):
        return FileResponse(ico_path)
    return FileResponse(_os.path.join(static_dir, "logo.png"))

if _os.getenv("SCREEN_STREAM_ENABLED", "false").lower() == "true":
    from app.screen_stream import router as screen_router
    app.include_router(screen_router)

@app.get("/antigravity", response_class=HTMLResponse, tags=["system"])
@app.get("/ag", response_class=HTMLResponse, tags=["system"])
async def antigravity_console() -> str:
    return ANTIGRAVITY_UI

@app.get("/", response_class=HTMLResponse, tags=["system"])
async def root() -> str:
    return LAB_UI


@app.get("/chat", response_class=HTMLResponse, tags=["system"])
async def chat() -> str:
    return CHAT_UI


@app.get("/command", response_class=HTMLResponse, tags=["system"])
async def command_center() -> str:
    return LAB_UI


@app.get("/lab", response_class=HTMLResponse, tags=["system"])
async def improvement_lab() -> str:
    return LAB_UI


@app.get("/pandora", response_class=HTMLResponse, tags=["system"])
async def pandora() -> str:
    return PANDORA_UI


@app.get("/pandora-sw.js", response_class=FileResponse, tags=["system"])
async def pandora_service_worker() -> FileResponse:
    return FileResponse(
        _os.path.join(static_dir, "pandora", "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/v1/pandora/status", tags=["system"])
async def pandora_status(request: Request) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = get_settings()

    if request.state.prometheus_full_access:
        authentication = "prometheus"
    elif request.state.pandora_session is not None:
        authentication = "pandora"
    else:
        authentication = "required"

    return JSONResponse(
        content={
            "service": "prometheus",
            "status": "ok",
            "pandora_voice": "pending",
            "pandora_chat": "ready",
            "pandora_project_run": "ready",
            "pandora_offline_queue": "ready",
            "pandora_mission_control": "ready",
            "authentication": authentication,
            "remote_access": (
                "enabled"
                if settings.http_remote_access_enabled
                else "disabled"
            ),
            "pairing_code_allowed": bool(
                settings.http_remote_access_enabled
                and request.state.local_http_request
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/v1/pandora/pairing-code", tags=["system"])
async def create_pandora_pairing_code(request: Request) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = get_settings()

    if not request.state.local_http_request:
        raise HTTPException(
            status_code=403,
            detail=PANDORA_PAIRING_LOCAL_ONLY_DETAIL,
        )
    if not settings.http_remote_access_enabled:
        raise HTTPException(
            status_code=409,
            detail=PANDORA_REMOTE_ACCESS_REQUIRED_DETAIL,
        )

    manager = _pandora_sessions(request.app)
    code = manager.issue_pairing_code()
    return JSONResponse(
        content={
            "code": code,
            "expires_in": manager.pairing_ttl_seconds,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/v1/pandora/pair", tags=["system"])
async def pair_pandora_device(
    payload: PandoraPairRequest,
    request: Request,
) -> JSONResponse:
    manager = _pandora_sessions(request.app)
    try:
        token = manager.create_session(
            code=payload.code,
            device_name=payload.device_name,
        )
    except PandoraPairingRejectedError as exc:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_INVALID_DETAIL,
        ) from exc
    except PandoraDeviceLimitError as exc:
        raise HTTPException(
            status_code=409,
            detail=PANDORA_DEVICE_LIMIT_DETAIL,
        ) from exc

    response = JSONResponse(
        content={
            "authentication": "pandora",
            "expires_in": manager.session_ttl_seconds,
        },
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        key=PANDORA_SESSION_COOKIE_NAME,
        value=token,
        max_age=manager.session_ttl_seconds,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path=PANDORA_SESSION_COOKIE_PATH,
    )
    return response


@app.post(
    "/v1/pandora/chat",
    response_model=PandoraChatResponse,
    tags=["pandora"],
)
async def chat_with_pandora(
    payload: PandoraChatRequest,
    request: Request,
    response: Response,
) -> PandoraChatResponse:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    request_id = request.headers.get("X-Pandora-Request-ID")

    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        replay = manager.begin_idempotent(
            token,
            operation="chat",
            request_id=request_id,
            payload=payload.model_dump(mode="json"),
        )
    except PandoraRequestIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PandoraRequestConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replay is not None:
        replay["idempotent_replay"] = True
        response.headers["Cache-Control"] = "no-store"
        return PandoraChatResponse.model_validate(replay)

    try:
        session = manager.begin_chat_request(token)
    except PandoraChatBusyError as exc:
        manager.abort_idempotent(token, operation="chat", request_id=request_id)
        raise HTTPException(
            status_code=429,
            detail=PANDORA_CHAT_BUSY_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except PandoraChatRateLimitError as exc:
        manager.abort_idempotent(token, operation="chat", request_id=request_id)
        raise HTTPException(
            status_code=429,
            detail=PANDORA_CHAT_RATE_LIMIT_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    if session is None:
        manager.abort_idempotent(token, operation="chat", request_id=request_id)
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        messages = [
            ChatMessage(role=item.role, content=item.content)
            for item in payload.history
        ]
        messages.append(ChatMessage(role="user", content=payload.message))

        orchestrator: Orchestrator | None = getattr(
            request.app.state,
            "orchestrator",
            None,
        )
        if orchestrator is None:
            raise RuntimeError("Pandora orchestrator unavailable")

        result = await orchestrator.run(
            OrchestrateRequest(
                messages=messages,
                mode="auto",
                system_prompt=_PANDORA_CHAT_SYSTEM_PROMPT,
                max_output_tokens=1024,
                include_candidates=False,
                bypass_cache=False,
                usage_scope="pandora-chat",
            )
        )
        answer = result.answer.strip()
        if not answer:
            raise RuntimeError("Pandora returned an empty answer")

        result = PandoraChatResponse(answer=answer, idempotent_replay=False)
        canonical = result.model_dump(mode="json", exclude={"idempotent_replay"})
        if request_id is not None:
            first_payload = dict(canonical)
            first_payload["idempotent_replay"] = False
            manager.finish_idempotent(token, operation="chat", request_id=request_id, response=canonical)
            response_payload = first_payload
        else:
            response_payload = canonical
        response.headers["Cache-Control"] = "no-store"
        return JSONResponse(content=response_payload, headers={"Cache-Control": "no-store"})
    except (ValueError, RuntimeError) as exc:
        manager.abort_idempotent(token, operation="chat", request_id=request_id)
        raise HTTPException(
            status_code=503,
            detail=PANDORA_CHAT_UNAVAILABLE_DETAIL,
        ) from exc
    except Exception as exc:
        manager.abort_idempotent(token, operation="chat", request_id=request_id)
        raise HTTPException(
            status_code=500,
            detail=PANDORA_CHAT_UNAVAILABLE_DETAIL,
        ) from exc
    finally:
        manager.end_chat_request(token)


@app.get(
    "/v1/pandora/projects",
    response_model=PandoraProjectsResponse,
    tags=["pandora"],
)
async def list_pandora_projects(
    request: Request,
    response: Response,
) -> PandoraProjectsResponse:
    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        manager: WorkspaceProjectManager = request.app.state.workspace_projects
        projects_response = manager.list_projects()
        source_projects = projects_response.projects[:PANDORA_PROJECT_LIST_LIMIT]
        projects = [
            PandoraProjectSummary(
                name=project.name,
                workspace_path=project.workspace_path,
                project_types=list(project.project_types[:8]),
                dirty=bool(project.git.dirty),
            )
            for project in source_projects
        ]
        response.headers["Cache-Control"] = "no-store"
        return PandoraProjectsResponse(
            projects=projects,
            truncated=(
                projects_response.truncated
                or len(projects_response.projects) > len(projects)
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL,
        ) from exc


@app.post(
    "/v1/pandora/project-run/preview",
    response_model=PandoraProjectRunPreviewResponse,
    tags=["pandora"],
)
async def preview_pandora_project_run(
    payload: PandoraProjectRunPreviewRequest,
    request: Request,
    response: Response,
) -> PandoraProjectRunPreviewResponse:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    request_id = request.headers.get("X-Pandora-Request-ID")
    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        replay = manager.begin_idempotent(
            token,
            operation="project_run_preview",
            request_id=request_id,
            payload=payload.model_dump(mode="json"),
        )
    except PandoraRequestIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PandoraRequestConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replay is not None:
        replay["idempotent_replay"] = True
        response.headers["Cache-Control"] = "no-store"
        return PandoraProjectRunPreviewResponse.model_validate(replay)

    try:
        session = manager.begin_project_run_request(token)
    except PandoraProjectRunBusyError as exc:
        manager.abort_idempotent(token, operation="project_run_preview", request_id=request_id)
        raise HTTPException(
            status_code=429,
            detail=PANDORA_PROJECT_RUN_BUSY_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except PandoraProjectRunRateLimitError as exc:
        manager.abort_idempotent(token, operation="project_run_preview", request_id=request_id)
        raise HTTPException(
            status_code=429,
            detail=PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    if session is None:
        manager.abort_idempotent(token, operation="project_run_preview", request_id=request_id)
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        supervisor: SupervisorService = request.app.state.supervisor
        preview = await supervisor.preview_project_run(
            ProjectRunPreviewRequest(
                goal=payload.goal,
                workspace_path=payload.workspace_path,
            )
        )
        if (
            len(preview.tasks) > PANDORA_PROJECT_RUN_MAX_TASKS
            or len(preview.exact_files) > PANDORA_PROJECT_RUN_MAX_FILES
        ):
            raise ValueError("Pandora Project Run preview scope is too large")

        manager.remember_project_run_preview(
            token,
            preview_digest=preview.preview_digest,
            goal=preview.goal,
            workspace_path=preview.workspace_path,
        )
        response.headers["Cache-Control"] = "no-store"
        result = PandoraProjectRunPreviewResponse(
            goal=preview.goal,
            workspace_path=preview.workspace_path,
            tasks=[
                PandoraProjectRunPreviewTask(
                    title=task.title,
                    exact_files=list(task.exact_files),
                    verification=task.verification,
                )
                for task in preview.tasks
            ],
            exact_files=list(preview.exact_files),
            task_count=len(preview.tasks),
            exact_file_count=len(preview.exact_files),
            requires_approval=True,
            side_effect_free=True,
            preview_digest=preview.preview_digest,
            expires_in=manager.project_run_preview_ttl_seconds,
            idempotent_replay=False,
        )
        canonical = result.model_dump(mode="json", exclude={"idempotent_replay"})
        if request_id is not None:
            first_payload = dict(canonical)
            first_payload["idempotent_replay"] = False
            manager.finish_idempotent(token, operation="project_run_preview", request_id=request_id, response=canonical)
            response_payload = first_payload
        else:
            response_payload = canonical
        return JSONResponse(content=response_payload, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        manager.abort_idempotent(token, operation="project_run_preview", request_id=request_id)
        raise HTTPException(
            status_code=422,
            detail=(
                "Project Run açıklaması veya workspace seçimi güvenli bir "
                "önizleme oluşturamadı."
            ),
        ) from exc
    except Exception as exc:
        manager.abort_idempotent(token, operation="project_run_preview", request_id=request_id)
        raise HTTPException(
            status_code=503,
            detail=PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL,
        ) from exc
    finally:
        manager.end_project_run_request(token)


@app.post(
    "/v1/pandora/project-run/commit",
    response_model=PandoraProjectRunCommitResponse,
    tags=["pandora"],
)
async def commit_pandora_project_run(
    payload: PandoraProjectRunCommitRequest,
    request: Request,
    response: Response,
) -> PandoraProjectRunCommitResponse:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )
    if not manager.project_run_preview_is_valid(
        token,
        preview_digest=payload.preview_digest,
        goal=payload.goal,
        workspace_path=payload.workspace_path,
    ):
        raise HTTPException(
            status_code=409,
            detail=PANDORA_PROJECT_RUN_PREVIEW_REQUIRED_DETAIL,
        )

    try:
        session = manager.begin_project_run_request(token)
    except PandoraProjectRunBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail=PANDORA_PROJECT_RUN_BUSY_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except PandoraProjectRunRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    if session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        supervisor: SupervisorService = request.app.state.supervisor
        committed = await supervisor.commit_project_run(
            ProjectRunCommitRequest(
                goal=payload.goal,
                workspace_path=payload.workspace_path,
                preview_digest=payload.preview_digest,
                autonomy_mode="locked",
                background=True,
                force_new=False,
            )
        )
        manager.register_project_run(token, committed.command_id)
        response.headers["Cache-Control"] = "no-store"
        return PandoraProjectRunCommitResponse(
            command_id=committed.command_id,
            status=committed.status,
            goal=committed.goal,
            workspace_path=committed.workspace_path,
            task_count=len(committed.task_ids),
            requires_desktop_approval=True,
            execution_started=False,
            created=committed.created,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Project Run oluşturulamadı. Önizleme güncelliğini veya "
                "masaüstündeki etkin görevi kontrol et."
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL,
        ) from exc
    finally:
        manager.end_project_run_request(token)


@app.get(
    "/v1/pandora/project-run/latest",
    response_model=PandoraProjectRunStatusResponse,
    tags=["pandora"],
)
async def read_latest_pandora_project_run(
    request: Request,
    response: Response,
) -> PandoraProjectRunStatusResponse:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )
    command_id = manager.latest_project_run_id(token)
    if command_id is None:
        raise HTTPException(
            status_code=404,
            detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL,
        )
    return await read_pandora_project_run(
        command_id=command_id,
        request=request,
        response=response,
    )


async def _pandora_mission_control_projection(*, manager, supervisor, token: str, command_id: str) -> dict:
    command = await supervisor.get(command_id)
    mission = await supervisor.get_mission_state_projection(command_id)
    terminal = bool(command.archived or command.status in {"completed", "failed", "cancelled", "reverted"})
    approval_task = next((task for task in command.tasks if task.status == "awaiting_approval" and task.approval_state == "pending" and task.approval_id and task.approval_version >= 1), None)
    approval = None
    if approval_task is not None:
        exact_files = sorted({path.replace("\\", "/") for path in approval_task.exact_files if isinstance(path, str) and path and not path.startswith(("/", "\\")) and ":" not in path})
        control_token = manager.mobile_approval_token(token, command_id=command_id, approval_id=approval_task.approval_id, approval_version=approval_task.approval_version)
        if control_token:
            approval = {"available": True, "task_title": str(approval_task.title)[:240], "exact_files": exact_files, "exact_file_count": len(exact_files), "control_token": control_token}
    can_pause = not terminal and command.status not in {"paused"} and not bool(getattr(command, "pause_requested", False))
    can_resume = command.status == "paused" and bool(getattr(command, "active_checkpoint_id", None)) and not terminal
    return {
        "revision": PANDORA_MISSION_CONTROL_REVISION,
        "command_id": command.id,
        "status": command.status,
        "terminal": terminal,
        "goal": command.goal,
        "workspace_path": command.project_run_workspace_path or ".",
        "progress_percent": round((sum(task.status == "completed" for task in command.tasks) / len(command.tasks)) * 100) if command.tasks else 0,
        "completed_tasks": sum(task.status == "completed" for task in command.tasks),
        "total_tasks": len(command.tasks),
        "waiting_approval_tasks": sum(task.status == "awaiting_approval" or task.approval_state == "pending" for task in command.tasks),
        "approval": approval,
        "mission": {"state": mission.command_status or command.status, "can_pause": can_pause, "can_resume": can_resume},
        "tasks": [{"title": str(task.title)[:240], "status": task.status, "approval_state": task.approval_state, "exact_file_count": len(task.exact_files)} for task in command.tasks],
    }


def _require_pandora_owner(request: Request, manager, token: str | None, command_id: str) -> None:
    if request.state.pandora_session is None:
        raise HTTPException(status_code=401, detail=PANDORA_PAIRING_REQUIRED_DETAIL)
    if not manager.owns_project_run(token, command_id):
        raise HTTPException(status_code=404, detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL)


@app.get("/v1/pandora/project-run/{command_id}/mission-control", tags=["pandora"])
async def read_pandora_mission_control(command_id: str, request: Request, response: Response) -> dict:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    _require_pandora_owner(request, manager, token, command_id)
    try:
        result = await _pandora_mission_control_projection(manager=manager, supervisor=request.app.state.supervisor, token=token, command_id=command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL) from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.post("/v1/pandora/project-run/{command_id}/approval", tags=["pandora"])
async def decide_pandora_approval(command_id: str, payload: PandoraApprovalDecisionRequest, request: Request, response: Response) -> dict:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    _require_pandora_owner(request, manager, token, command_id)
    try:
        if not manager.begin_mobile_control(token, command_id):
            raise HTTPException(status_code=404, detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL)
    except PandoraMobileControlBusyError as exc:
        raise HTTPException(status_code=409, detail="Pandora Mission Control işlemi zaten sürüyor.") from exc
    try:
        command = await request.app.state.supervisor.get(command_id)
        task = next((item for item in command.tasks if item.status == "awaiting_approval" and item.approval_state == "pending" and item.approval_id and item.approval_version >= 1), None)
        if task is None or not manager.mobile_approval_token_is_valid(token, command_id=command_id, approval_id=task.approval_id, approval_version=task.approval_version, control_token=payload.control_token):
            raise HTTPException(status_code=409, detail="Pandora mobile approval is stale. Refresh Mission Control.")
        if payload.decision == "approve":
            await request.app.state.supervisor.approve(command_id=command_id, task_id=task.id, expected_approval_id=task.approval_id, expected_approval_version=task.approval_version, background=False)
        else:
            await request.app.state.supervisor.reject(command_id=command_id, task_id=task.id, expected_approval_id=task.approval_id, expected_approval_version=task.approval_version)
        result = await _pandora_mission_control_projection(manager=manager, supervisor=request.app.state.supervisor, token=token, command_id=command_id)
        response.headers["Cache-Control"] = "no-store"
        return result
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Pandora mobile approval is stale. Refresh Mission Control.") from exc
    finally:
        manager.end_mobile_control(token, command_id)


@app.post("/v1/pandora/project-run/{command_id}/pause", tags=["pandora"])
async def pause_pandora_mission(command_id: str, request: Request, response: Response) -> dict:
    manager = _pandora_sessions(request.app); token = request_pandora_session_token(request); _require_pandora_owner(request, manager, token, command_id)
    try:
        if not manager.begin_mobile_control(token, command_id): raise HTTPException(status_code=404, detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL)
    except PandoraMobileControlBusyError as exc: raise HTTPException(status_code=409, detail="Pandora Mission Control işlemi zaten sürüyor.") from exc
    try:
        command = await request.app.state.supervisor.get(command_id)
        if command.status in {"paused", "completed", "failed", "cancelled", "reverted"} or getattr(command, "pause_requested", False): raise HTTPException(status_code=409, detail="Pandora Mission Control durumu pause için uygun değil.")
        await request.app.state.supervisor.request_mission_pause(command_id, expected_control_version=command.control_version)
        response.headers["Cache-Control"] = "no-store"
        return await _pandora_mission_control_projection(manager=manager, supervisor=request.app.state.supervisor, token=token, command_id=command_id)
    except HTTPException: raise
    except (KeyError, ValueError) as exc: raise HTTPException(status_code=409, detail="Pandora Mission Control durumu pause için uygun değil.") from exc
    finally: manager.end_mobile_control(token, command_id)


@app.post("/v1/pandora/project-run/{command_id}/resume", tags=["pandora"])
async def resume_pandora_mission(command_id: str, request: Request, response: Response) -> dict:
    manager = _pandora_sessions(request.app); token = request_pandora_session_token(request); _require_pandora_owner(request, manager, token, command_id)
    try:
        if not manager.begin_mobile_control(token, command_id): raise HTTPException(status_code=404, detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL)
    except PandoraMobileControlBusyError as exc: raise HTTPException(status_code=409, detail="Pandora Mission Control işlemi zaten sürüyor.") from exc
    try:
        command = await request.app.state.supervisor.get(command_id)
        checkpoint_id = getattr(command, "active_checkpoint_id", None)
        if command.status != "paused" or not checkpoint_id: raise HTTPException(status_code=409, detail="Pandora Mission Control durumu resume için uygun değil.")
        await request.app.state.supervisor.resume_mission(command_id, checkpoint_id=checkpoint_id, expected_control_version=command.control_version)
        response.headers["Cache-Control"] = "no-store"
        return await _pandora_mission_control_projection(manager=manager, supervisor=request.app.state.supervisor, token=token, command_id=command_id)
    except HTTPException: raise
    except (KeyError, ValueError) as exc: raise HTTPException(status_code=409, detail="Pandora Mission Control durumu resume için uygun değil.") from exc
    finally: manager.end_mobile_control(token, command_id)


@app.get(
    "/v1/pandora/project-run/{command_id}",
    response_model=PandoraProjectRunStatusResponse,
    tags=["pandora"],
)
async def read_pandora_project_run(
    command_id: str,
    request: Request,
    response: Response,
) -> PandoraProjectRunStatusResponse:
    manager = _pandora_sessions(request.app)
    token = request_pandora_session_token(request)
    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )
    if not manager.owns_project_run(token, command_id):
        raise HTTPException(
            status_code=404,
            detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL,
        )

    try:
        supervisor: SupervisorService = request.app.state.supervisor
        command = await supervisor.get(command_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL,
        ) from exc

    if not command.project_run_preview_digest:
        raise HTTPException(
            status_code=404,
            detail=PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL,
        )

    total_tasks = len(command.tasks)
    completed_tasks = sum(task.status == "completed" for task in command.tasks)
    failed_tasks = sum(task.status == "failed" for task in command.tasks)
    waiting_approval_tasks = sum(
        task.status == "awaiting_approval" or task.approval_state == "pending"
        for task in command.tasks
    )
    progress_percent = (
        round((completed_tasks / total_tasks) * 100)
        if total_tasks
        else 0
    )
    terminal = bool(
        command.archived or command.status in {"completed", "failed"}
    )
    response.headers["Cache-Control"] = "no-store"
    return PandoraProjectRunStatusResponse(
        command_id=command.id,
        goal=command.goal,
        workspace_path=command.project_run_workspace_path or ".",
        status=command.status,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        waiting_approval_tasks=waiting_approval_tasks,
        progress_percent=progress_percent,
        requires_desktop_approval=waiting_approval_tasks > 0,
        terminal=terminal,
        tasks=[
            PandoraProjectRunTaskStatus(
                title=task.title,
                status=task.status,
                approval_state=task.approval_state,
                exact_file_count=len(task.exact_files),
            )
            for task in command.tasks
        ],
    )


@app.post("/v1/pandora/logout", status_code=204, tags=["system"])
async def logout_pandora_device(request: Request) -> Response:
    manager = _pandora_sessions(request.app)
    manager.revoke(request_pandora_session_token(request))
    response = Response(
        status_code=204,
        headers={"Cache-Control": "no-store"},
    )
    response.delete_cookie(
        key=PANDORA_SESSION_COOKIE_NAME,
        path=PANDORA_SESSION_COOKIE_PATH,
        samesite="strict",
    )
    return response


@app.get("/arena", response_class=HTMLResponse, tags=["arena"])
async def arena_dashboard() -> str:
    return ARENA_UI


def _arena_history_reader() -> ArenaHistoryReader:
    settings = app.state.settings
    return ArenaHistoryReader(
        settings.arena_history_directory,
        max_databases=settings.arena_history_max_databases,
    )


def _arena_recovery_executor() -> ArenaRecoveryExecutor:
    executor = getattr(app.state, "arena_recovery_executor", None)
    if executor is not None:
        return executor
    settings = app.state.settings
    executor = ArenaRecoveryExecutor(
        project_root=Path.cwd(),
        workspace_root=settings.workspace_root / "arena-recovery",
        history_directory=settings.arena_history_directory,
    )
    app.state.arena_recovery_executor = executor
    return executor


@app.get("/v1/arena/scenarios", tags=["arena"])
async def arena_scenarios() -> list[dict[str, object]]:
    return [
        {
            "id": scenario.id,
            "title": scenario.title,
            "required_agents": list(scenario.required_agents),
            "minimum_handoffs": scenario.minimum_handoffs,
            "max_model_calls": scenario.max_model_calls,
            "target_total_tokens": scenario.target_total_tokens,
        }
        for scenario in list_scenarios()
    ]


@app.get("/v1/arena/history", tags=["arena"])
async def arena_history(
    scenario_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    return _arena_history_reader().history(
        scenario_id=scenario_id,
        limit=max(1, min(limit, 200)),
    )


@app.get("/v1/arena/compare", tags=["arena"])
async def arena_compare(
    base_run_id: str,
    candidate_run_id: str,
) -> dict[str, object]:
    base_id = base_run_id.strip()
    candidate_id = candidate_run_id.strip()
    if not base_id or not candidate_id:
        raise HTTPException(
            status_code=422,
            detail="İki Arena koşusu kimliği de gereklidir.",
        )
    if base_id == candidate_id:
        raise HTTPException(
            status_code=422,
            detail="Karşılaştırma için iki farklı Arena koşusu seçin.",
        )

    reader = _arena_history_reader()
    base = reader.get(base_id)
    candidate = reader.get(candidate_id)
    missing = [
        run_id
        for run_id, result in (
            (base_id, base),
            (candidate_id, candidate),
        )
        if result is None
    ]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Arena koşusu bulunamadı: {', '.join(missing)}",
        )
    assert base is not None
    assert candidate is not None
    return compare_arena_runs(base, candidate)


@app.get("/v1/arena/runs/{run_id}/diagnosis", tags=["arena"])
async def arena_run_diagnosis(run_id: str) -> dict[str, object]:
    result = _arena_history_reader().get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Arena koşusu bulunamadı.")
    return diagnose_arena_run(result)


@app.get("/v1/arena/runs/{run_id}/recovery-plan", tags=["arena"])
async def arena_run_recovery_plan(run_id: str) -> dict[str, object]:
    result = _arena_history_reader().get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Arena koşusu bulunamadı.")
    diagnosis = diagnose_arena_run(result)
    known_scenarios = {scenario.id for scenario in list_scenarios()}
    return build_arena_recovery_plan(
        result,
        diagnosis,
        known_scenarios=known_scenarios,
    )


@app.post(
    "/v1/arena/runs/{run_id}/recovery-executions",
    tags=["arena"],
    status_code=202,
)
async def start_arena_recovery_execution(
    run_id: str,
    request: ArenaRecoveryExecutionRequest,
) -> dict[str, object]:
    result = _arena_history_reader().get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Arena koşusu bulunamadı.")
    diagnosis = diagnose_arena_run(result)
    known_scenarios = {scenario.id for scenario in list_scenarios()}
    plan = build_arena_recovery_plan(
        result,
        diagnosis,
        known_scenarios=known_scenarios,
    )
    try:
        return await _arena_recovery_executor().start(
            source_run=result,
            recovery_plan=plan,
            approval_phrase=request.approval_phrase,
        )
    except ArenaRecoveryApprovalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ArenaRecoveryUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArenaRecoveryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArenaRecoveryQuotaError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.get(
    "/v1/arena/recovery-executions/{execution_id}",
    tags=["arena"],
)
async def arena_recovery_execution(
    execution_id: str,
) -> dict[str, object]:
    execution = _arena_recovery_executor().get(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=404,
            detail="Arena recovery yürütmesi bulunamadı.",
        )
    return execution


@app.get("/v1/arena/runs/{run_id}", tags=["arena"])
async def arena_run(run_id: str) -> dict[str, object]:
    result = _arena_history_reader().get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Arena koşusu bulunamadı.")
    return result


def _workspace_policy() -> WorkspacePolicy:
    settings = app.state.settings
    return WorkspacePolicy(
        root=settings.workspace_root,
        max_file_bytes=settings.workspace_max_file_bytes,
        max_search_results=settings.workspace_max_search_results,
    )


@app.get("/v1/workspace/files", tags=["workspace"])
async def workspace_files() -> list[dict[str, object]]:
    policy = _workspace_policy()
    return [
        {
            "path": policy.relative(path),
            "size_bytes": path.stat().st_size,
        }
        for path in policy.iter_files(policy.root)
    ]


@app.get(
    "/workspace-preview/{file_path:path}",
    response_class=FileResponse,
    include_in_schema=False,
)
async def workspace_preview(file_path: str) -> FileResponse:
    policy = _workspace_policy()
    try:
        path = policy.resolve(file_path, must_exist=True)
        policy.ensure_text_file(path)
    except (ToolError, OSError, UnicodeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path)


@app.get("/v1/improvement/status", tags=["improvement"])
async def improvement_status() -> dict:
    return await app.state.improvement.status()


@app.get("/v1/improvement/episodes", tags=["improvement"])
async def improvement_episodes(limit: int = 100) -> list[dict]:
    return await app.state.improvement.list_rows(
        "experience_episodes",
        limit=max(1, min(limit, 1_000)),
    )


@app.get("/v1/improvement/strategies", tags=["improvement"])
async def improvement_strategies(limit: int = 100) -> list[dict]:
    return await app.state.improvement.list_rows(
        "strategy_cards",
        limit=max(1, min(limit, 1_000)),
    )


@app.post("/v1/improvement/recall", tags=["improvement"])
async def improvement_recall(request: RecallRequest) -> dict:
    capsule = await app.state.improvement.recall(
        query=request.query,
        target_path=request.target_path,
        max_chars=request.max_chars,
    )
    return {
        "text": capsule.text,
        "task_signature": capsule.task_signature,
        "strategy_ids": capsule.strategy_ids,
        "orientation_ids": capsule.orientation_ids,
        "chars": capsule.chars,
        "lexical_only": capsule.lexical_only,
    }


@app.post("/v1/improvement/index", tags=["improvement"])
async def improvement_index() -> dict:
    return await app.state.improvement.index_workspace()


@app.get("/v1/improvement/candidates", tags=["improvement"])
async def improvement_candidates(limit: int = 100) -> list[dict]:
    return await app.state.improvement.list_rows(
        "improvement_candidates",
        limit=max(1, min(limit, 1_000)),
    )


@app.post("/v1/improvement/candidates", tags=["improvement"])
async def create_improvement_candidate(
    request: CandidateCreateRequest,
) -> dict:
    try:
        return await app.state.forge.create(
            kind=request.kind,
            title=request.title,
            payload=request.payload,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/improvement/candidates/suggest", tags=["improvement"])
async def suggest_improvement_candidates() -> list[dict]:
    return await app.state.forge.suggest_from_failures()


@app.post(
    "/v1/improvement/candidates/{candidate_id}/evaluate",
    tags=["improvement"],
)
async def evaluate_improvement_candidate(candidate_id: str) -> dict:
    try:
        return await app.state.forge.evaluate(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/improvement/candidates/{candidate_id}/promote",
    tags=["improvement"],
)
async def promote_improvement_candidate(
    candidate_id: str,
    request: CandidatePromoteRequest,
) -> dict:
    try:
        return await app.state.forge.promote(
            candidate_id,
            confirmation=request.confirmation,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/improvement/candidates/{candidate_id}/rollback",
    tags=["improvement"],
)
async def rollback_improvement_candidate(candidate_id: str) -> dict:
    try:
        return await app.state.forge.rollback(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/improvement/benchmark/run", tags=["improvement"])
async def run_improvement_benchmark(
    request: BenchmarkRunRequest | None = None,
) -> dict:
    try:
        return await app.state.forge.run_benchmark(
            request.candidate_id if request else None
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
@app.get("/v1/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    settings = app.state.settings
    registry: ProviderRegistry = app.state.registry
    catalog: RouteCatalog = app.state.catalog

    providers = [
        ProviderInfo(
            name=name,
            enabled=provider is not None,
            model=provider.default_model if provider else None,
        )
        for name, provider in registry.provider_slots().items()
    ]
    routes = [
        RouteInfo(
            route_key=route.key,
            provider=route.provider,
            model=route.model,
            enabled=catalog.is_enabled(route),
            label=route.label,
        )
        for route in catalog.all()
    ]
    return HealthResponse(
        status="ok",
        providers=providers,
        routes=routes,
        tools=app.state.tools.names(),
        agents=app.state.agents.ids(),
        skills=app.state.skills.ids(),
        workspace_root=str(settings.workspace_root.expanduser().resolve()),
        paid_models_enabled=settings.effective_paid_models_enabled,
    )


@app.get("/v1/workspace", response_model=WorkspaceStatus, tags=["workspace"])
async def workspace_status() -> WorkspaceStatus:
    settings = app.state.settings
    summary = await app.state.tools.execute("project_summary", {})
    active = app.state.workspace_projects.read_active()
    return WorkspaceStatus(
        root=str(settings.workspace_root.expanduser().resolve()),
        exists=settings.workspace_root.expanduser().resolve().exists(),
        project_types=summary["project_types"],
        git_repository=summary["git_repository"],
        paid_models_enabled=settings.effective_paid_models_enabled,
        active_workspace_path=active.binding.workspace_path if active.binding else None,
        active_project_key=active.binding.project_key if active.binding else None,
    )


@app.get("/v1/tools", response_model=list[ToolInfo], tags=["agent"])
async def tools() -> list[ToolInfo]:
    return [
        ToolInfo(**definition)
        for definition in app.state.tools.definitions()
    ]


@app.get("/v1/agents", response_model=list[AgentProfile], tags=["agents"])
async def list_agents() -> list[AgentProfile]:
    return app.state.agents.all()


@app.get("/v1/skills", response_model=SkillCatalogResponse, tags=["skills"])
async def list_skills(response: Response) -> SkillCatalogResponse:
    try:
        result = app.state.skills.catalog()
    except SkillManifestError as exc:
        raise HTTPException(status_code=503, detail="Skill manifest catalog is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.get("/v1/skills/{skill_id}", response_model=SkillManifestView, tags=["skills"])
async def read_skill(skill_id: str, response: Response) -> SkillManifestView:
    try:
        result = app.state.skills.get(skill_id)
    except SkillManifestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Skill manifest not found.") from exc
    except SkillManifestError as exc:
        raise HTTPException(status_code=503, detail="Skill manifest catalog is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result

@app.get("/v1/agents/{agent_id}", response_model=AgentProfile, tags=["agents"])
async def read_agent(agent_id: str) -> AgentProfile:
    try: return app.state.agents.get(agent_id)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.post("/v1/agents/{agent_id}/run", response_model=AgentResponse, tags=["agents"])
async def run_selected_agent(agent_id: str, request: AgentRequest) -> AgentResponse:
    try: return await app.state.agent.run(request.model_copy(update={"agent_id": agent_id}))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.post("/v1/agent/run", response_model=AgentResponse, tags=["agent"])
async def run_agent(request: AgentRequest) -> AgentResponse:
    agent: AgentEngine = app.state.agent
    try:
        return await agent.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Agent çalışırken beklenmeyen sunucu hatası oluştu.",
        ) from exc


@app.post(
    "/v1/agent/{session_id}/approve/{approval_id}",
    response_model=AgentResponse,
    tags=["agent"],
)
async def approve_agent_action(
    session_id: str,
    approval_id: str,
) -> AgentResponse:
    try:
        return await app.state.agent.approve(
            session_id=session_id,
            approval_id=approval_id,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc).strip() or type(exc).__name__
        raise HTTPException(status_code=503, detail=detail) from exc
    except Exception as exc:
        detail = str(exc).strip() or (
            f"{type(exc).__name__}: ayrıntı vermeyen sistem hatası"
        )
        raise HTTPException(status_code=500, detail=detail) from exc


@app.post(
    "/v1/agent/{session_id}/reject/{approval_id}",
    response_model=AgentResponse,
    tags=["agent"],
)
async def reject_agent_action(
    session_id: str,
    approval_id: str,
) -> AgentResponse:
    try:
        return await app.state.agent.reject(
            session_id=session_id,
            approval_id=approval_id,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/v1/providers/github/models",
    response_model=ModelCatalogResponse,
    tags=["providers"],
)
async def github_models() -> ModelCatalogResponse:
    provider = app.state.registry.get_optional("github")
    if provider is None:
        raise HTTPException(status_code=503, detail="GitHub etkin değil.")
    try:
        models = await provider.list_models()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ModelCatalogResponse(provider="github", models=models)


@app.get(
    "/v1/providers/groq/models",
    response_model=ModelCatalogResponse,
    tags=["providers"],
)
async def groq_models() -> ModelCatalogResponse:
    provider = app.state.registry.get_optional("groq")
    if provider is None:
        raise HTTPException(status_code=503, detail="Groq etkin değil.")
    try:
        models = await provider.list_models()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ModelCatalogResponse(provider="groq", models=models)


@app.post(
    "/v1/supervisor/commands",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def create_supervisor_command(
    request: SupervisorCreateRequest,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.create(
            goal=request.goal,
            routing_mode=request.routing_mode,
            provider=request.provider,
            auto_start=request.auto_start,
            background=request.background,
            autonomy_mode=request.autonomy_mode,
            force_new=getattr(request, "force_new", False),
            workspace_path=request.workspace_path,
        )
    except TrustedAutonomyDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/project-run/preview",
    response_model=ProjectRunPreviewResponse,
    tags=["supervisor"],
)
async def preview_project_run(
    payload: ProjectRunPreviewRequest,
) -> ProjectRunPreviewResponse:
    try:
        return await app.state.supervisor.preview_project_run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/project-run/commit",
    response_model=ProjectRunCommitResponse,
    tags=["supervisor"],
)
async def commit_project_run(
    payload: ProjectRunCommitRequest,
) -> ProjectRunCommitResponse:
    try:
        return await app.state.supervisor.commit_project_run(payload)
    except ValueError as exc:
        err_msg = str(exc)
        if "stale_project_run_preview" in err_msg or "aktif bir görev/komut çalışıyor" in err_msg:
            raise HTTPException(status_code=409, detail=err_msg) from exc
        raise HTTPException(status_code=422, detail=err_msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/change-review",
    response_model=RunChangeReviewResponse,
    tags=["supervisor"],
)
async def read_supervisor_change_review(
    command_id: str,
) -> RunChangeReviewResponse:
    try:
        return await app.state.supervisor.get_command_change_review(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Komut bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/revert",
    response_model=RunRevertResponse,
    tags=["supervisor"],
)
async def revert_supervisor_command_changes(
    command_id: str,
    payload: RunRevertRequest,
) -> RunRevertResponse:
    try:
        return await app.state.supervisor.revert_command_changes(
            command_id=command_id,
            request=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Komut bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/v1/workspace/projects",
    response_model=WorkspaceProjectsResponse,
    tags=["workspace"],
)
async def list_workspace_projects(response: Response) -> WorkspaceProjectsResponse:
    try:
        manager: WorkspaceProjectManager = app.state.workspace_projects
        result = manager.list_projects()
        response.headers["Cache-Control"] = "no-store"
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/v1/workspace/projects/select",
    response_model=WorkspaceProjectSelectResponse,
    tags=["workspace"],
)
async def select_workspace_project(
    response: Response,
    payload: WorkspaceProjectSelectRequest,
) -> WorkspaceProjectSelectResponse:
    try:
        manager: WorkspaceProjectManager = app.state.workspace_projects
        result = manager.select_project(payload)
        response.headers["Cache-Control"] = "no-store"
        return result
    except ProjectWorkspaceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProjectWorkspaceConflictError, ProjectWorkspaceIntegrityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectWorkspaceStorageError as exc:
        raise HTTPException(status_code=503, detail="Workspace state unavailable.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/v1/workspace/projects/active", response_model=ProjectWorkspaceActiveResponse, tags=["workspace"])
async def read_active_workspace_project(response: Response) -> ProjectWorkspaceActiveResponse:
    try:
        result = app.state.workspace_projects.read_active()
    except ProjectWorkspaceIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectWorkspaceError as exc:
        raise HTTPException(status_code=503, detail="Workspace state unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.get(
    "/v1/workspace/project-dna",
    response_model=ProjectDNAResponse,
    tags=["workspace"],
)
async def read_workspace_project_dna(
    response: Response,
    workspace_path: str = ".",
) -> ProjectDNAResponse:
    manager: ProjectDNAManager = app.state.project_dna
    try:
        result = manager.read(workspace_path)
    except ProjectDNAValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProjectDNAIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectDNAError as exc:
        raise HTTPException(status_code=503, detail="Project DNA is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.put(
    "/v1/workspace/project-dna",
    response_model=ProjectDNAResponse,
    tags=["workspace"],
)
async def update_workspace_project_dna(
    payload: ProjectDNAUpdateRequest,
    response: Response,
) -> ProjectDNAResponse:
    manager: ProjectDNAManager = app.state.project_dna
    try:
        result = manager.update(payload)
    except ProjectDNAValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProjectDNAConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectDNAIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectDNAError as exc:
        raise HTTPException(status_code=503, detail="Project DNA is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.get(
    "/v1/workspace/decision-memory",
    response_model=DecisionMemoryPage,
    tags=["workspace"],
)
async def list_workspace_decision_memory(
    response: Response,
    workspace_path: str = ".",
    active_only: bool = True,
    scope_kind: DecisionMemoryScopeKind | None = None,
    after_revision: int | None = None,
    limit: int = 50,
) -> DecisionMemoryPage:
    try:
        result = app.state.decision_memory.list(workspace_path=workspace_path, active_only=active_only, scope_kind=scope_kind, after_revision=after_revision, limit=limit)
    except DecisionMemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DecisionMemoryIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionMemoryError as exc:
        raise HTTPException(status_code=503, detail="Decision Memory is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.get(
    "/v1/workspace/decision-memory/decisions/{decision_id}",
    response_model=DecisionMemoryRecord,
    tags=["workspace"],
)
async def read_workspace_decision_memory_record(
    decision_id: str,
    response: Response,
    workspace_path: str = ".",
) -> DecisionMemoryRecord:
    try:
        result = app.state.decision_memory.read(workspace_path=workspace_path, decision_id=decision_id)
    except DecisionMemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DecisionMemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DecisionMemoryIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionMemoryError as exc:
        raise HTTPException(status_code=503, detail="Decision Memory is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.post(
    "/v1/workspace/decision-memory/decisions",
    response_model=DecisionMemoryWriteResponse,
    tags=["workspace"],
)
async def create_workspace_decision_memory_record(
    payload: DecisionMemoryCreateRequest,
    response: Response,
) -> DecisionMemoryWriteResponse:
    try:
        result = app.state.decision_memory.create(payload)
    except DecisionMemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DecisionMemoryConflictError, DecisionMemoryIntegrityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionMemoryError as exc:
        raise HTTPException(status_code=503, detail="Decision Memory is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.post(
    "/v1/supervisor/commands/{command_id}/decisions/{decision_id}/remember",
    response_model=DecisionMemoryWriteResponse,
    tags=["supervisor"],
)
async def remember_supervisor_decision(
    command_id: str,
    decision_id: str,
    payload: SupervisorDecisionRememberRequest,
    response: Response,
) -> DecisionMemoryWriteResponse:
    try:
        result = await app.state.supervisor.remember_decision(command_id=command_id, decision_id=decision_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Decision not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionMemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DecisionMemoryConflictError, DecisionMemoryIntegrityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DecisionMemoryError as exc:
        raise HTTPException(status_code=503, detail="Decision Memory is unavailable.") from exc
    response.headers["Cache-Control"] = "no-store"
    return result


@app.get(
    "/v1/supervisor/project-runs",
    response_model=ProjectRunHistoryResponse,
    tags=["supervisor"],
)
async def list_workspace_project_runs(
    workspace_path: str = ".",
    status: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> ProjectRunHistoryResponse:
    try:
        supervisor = app.state.supervisor
        return await supervisor.list_project_run_history(
            workspace_path=workspace_path,
            status_filter=status,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/tasks/{task_id}/retry-request",
    response_model=ProjectRunRetryResponse,
    tags=["supervisor"],
)
async def request_supervisor_project_run_task_retry(
    command_id: str,
    task_id: str,
    payload: ProjectRunRetryRequest,
) -> ProjectRunRetryResponse:
    try:
        supervisor = app.state.supervisor
        return await supervisor.request_project_run_task_retry(
            command_id=command_id,
            task_id=task_id,
            request=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc





@app.get(
    "/v1/supervisor/commands",
    response_model=list[SupervisorCommandSummary],
    tags=["supervisor"],
)
async def list_supervisor_commands() -> list[SupervisorCommandSummary]:
    commands = await app.state.supervisor.list()
    return [
        SupervisorCommandSummary(
            id=command.id,
            goal=command.goal,
            status=command.status,
            autonomy_mode=command.autonomy_mode,
            auto_run=command.auto_run,
            completed_tasks=sum(
                task.status == "completed"
                for task in command.tasks
            ),
            total_tasks=len(command.tasks),
            pending_decisions=sum(
                decision.status == "pending"
                for decision in command.decisions
            ),
            created_at=command.created_at,
            updated_at=command.updated_at,
            workspace_path=command.workspace_path,
        )
        for command in commands
    ]


@app.get(
    "/v1/supervisor/commands/{command_id}",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def read_supervisor_command(
    command_id: str,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.get(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/mission-events",
    response_model=MissionEventPage,
    tags=["supervisor"],
)
async def read_supervisor_mission_events(
    command_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> MissionEventPage:
    try:
        return await app.state.supervisor.list_mission_events(
            command_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionEventIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission event journal bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/history",
    response_model=MissionHistoryPage,
    tags=["supervisor"],
)
async def read_supervisor_mission_history(
    command_id: str,
    response: Response,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> MissionHistoryPage:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await app.state.supervisor.get_mission_history(
            command_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        MissionHistoryIntegrityError,
        MissionEventIntegrityError,
        ExecutionReceiptIntegrityError,
        MissionCheckpointIntegrityError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission geçmişi bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/post-run-summary",
    response_model=MissionPostRunSummary,
    tags=["supervisor"],
)
async def read_supervisor_mission_post_run_summary(
    command_id: str,
    response: Response,
) -> MissionPostRunSummary:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await app.state.supervisor.get_mission_post_run_summary(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionHistoryLimitError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission geçmişi desteklenen kayıt sınırını aşıyor.",
        ) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/branches",
    response_model=MissionBranchResponse,
    tags=["supervisor"],
)
async def create_supervisor_mission_branch(
    command_id: str,
    payload: CreateMissionBranchRequest,
    response: Response,
) -> MissionBranchResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await app.state.supervisor.create_mission_branch(command_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission veya checkpoint bulunamadı.") from exc
    except MissionBranchUnsupportedSnapshotError as exc:
        raise HTTPException(status_code=409, detail="Checkpoint session branching için uyumlu değil.") from exc
    except MissionBranchConflictError as exc:
        raise HTTPException(status_code=409, detail="Session branch isteği mevcut idempotency kaydıyla çakışıyor.") from exc
    except (MissionBranchIntegrityError, MissionCheckpointIntegrityError, MissionEventIntegrityError) as exc:
        raise HTTPException(status_code=409, detail="Session branching bütünlüğü doğrulanamadı.") from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/branch/activate",
    response_model=MissionControlResponse,
    tags=["supervisor"],
)
async def activate_supervisor_mission_branch(
    command_id: str,
    payload: ActivateMissionBranchRequest,
    response: Response,
) -> MissionControlResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await app.state.supervisor.activate_mission_branch(command_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission veya checkpoint bulunamadı.") from exc
    except (MissionCheckpointIntegrityError, MissionEventIntegrityError) as exc:
        raise HTTPException(status_code=409, detail="Session branching bütünlüğü doğrulanamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Session branch etkinleştirilemedi.") from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/lineage",
    response_model=MissionLineageResponse,
    tags=["supervisor"],
)
async def read_supervisor_mission_lineage(
    command_id: str,
    response: Response,
) -> MissionLineageResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await app.state.supervisor.get_mission_lineage(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission bulunamadı.") from exc
    except MissionBranchIntegrityError as exc:
        raise HTTPException(status_code=409, detail="Mission lineage bütünlüğü doğrulanamadı.") from exc
    except (
        MissionHistoryIntegrityError,
        MissionEventIntegrityError,
        ExecutionReceiptIntegrityError,
        MissionCheckpointIntegrityError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission geçmişi bütünlüğü doğrulanamadı.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="Post-run özeti yalnız tamamlanmış veya başarısız Mission'lar için kullanılabilir.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/mission-state",
    response_model=MissionStateProjection,
    tags=["supervisor"],
)
async def read_supervisor_mission_state(
    command_id: str,
) -> MissionStateProjection:
    try:
        return await app.state.supervisor.get_mission_state_projection(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionEventIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission event journal bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/execution-receipts",
    response_model=ExecutionReceiptPage,
    tags=["supervisor"],
)
async def read_supervisor_execution_receipts(
    command_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ExecutionReceiptPage:
    try:
        return await app.state.supervisor.list_execution_receipts(
            command_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Execution receipt bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/execution-receipts/{receipt_id}",
    response_model=ExecutionReceipt,
    tags=["supervisor"],
)
async def read_supervisor_execution_receipt(
    command_id: str,
    receipt_id: str,
) -> ExecutionReceipt:
    try:
        return await app.state.supervisor.get_execution_receipt(
            command_id=command_id,
            receipt_id=receipt_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionReceiptIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Execution receipt bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/checkpoints",
    response_model=MissionCheckpointPage,
    tags=["supervisor"],
)
async def read_supervisor_mission_checkpoints(
    command_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> MissionCheckpointPage:
    try:
        return await app.state.supervisor.list_mission_checkpoints(
            command_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionCheckpointIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission checkpoint bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/checkpoints/{checkpoint_id}",
    response_model=MissionCheckpointRecord,
    tags=["supervisor"],
)
async def read_supervisor_mission_checkpoint(
    command_id: str,
    checkpoint_id: str,
) -> MissionCheckpointRecord:
    try:
        return await app.state.supervisor.get_mission_checkpoint(
            command_id=command_id,
            checkpoint_id=checkpoint_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissionCheckpointIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission checkpoint bütünlüğü doğrulanamadı.",
        ) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/checkpoints",
    response_model=MissionCheckpointRecord,
    tags=["supervisor"],
)
async def create_supervisor_mission_checkpoint(
    command_id: str,
    body: CreateMissionCheckpointRequest = Body(default_factory=CreateMissionCheckpointRequest),
) -> MissionCheckpointRecord:
    try:
        return await app.state.supervisor.create_mission_checkpoint(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MissionCheckpointIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission checkpoint bütünlüğü doğrulanamadı.",
        ) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/pause",
    response_model=MissionControlResponse,
    tags=["supervisor"],
)
async def pause_supervisor_mission(
    command_id: str,
    body: PauseMissionRequest = Body(default_factory=PauseMissionRequest),
) -> MissionControlResponse:
    try:
        return await app.state.supervisor.request_mission_pause(
            command_id=command_id,
            reason=body.reason,
            expected_control_version=body.expected_control_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MissionCheckpointIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission checkpoint bütünlüğü doğrulanamadı.",
        ) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/resume",
    response_model=MissionControlResponse,
    tags=["supervisor"],
)
async def resume_supervisor_mission(
    command_id: str,
    body: ResumeMissionRequest = Body(default_factory=ResumeMissionRequest),
) -> MissionControlResponse:
    try:
        return await app.state.supervisor.resume_mission(
            command_id=command_id,
            checkpoint_id=body.checkpoint_id,
            expected_control_version=body.expected_control_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MissionCheckpointIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Mission checkpoint bütünlüğü doğrulanamadı.",
        ) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/recovery",
    response_model=MissionRecoveryStatusResponse,
    tags=["supervisor"],
)
async def read_supervisor_mission_recovery(
    command_id: str,
) -> MissionRecoveryStatusResponse:
    try:
        return await app.state.supervisor.get_mission_recovery_status(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission bulunamadı.") from exc
    except (MissionCheckpointIntegrityError, MissionEventIntegrityError, ExecutionReceiptIntegrityError) as exc:
        raise HTTPException(status_code=409, detail="Mission bütünlüğü doğrulanamadı.") from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/recover",
    response_model=RecoverMissionResponse,
    tags=["supervisor"],
)
async def recover_supervisor_mission(
    command_id: str,
    payload: RecoverMissionRequest,
) -> RecoverMissionResponse:
    try:
        return await app.state.supervisor.recover_mission(
            command_id,
            failure_id=payload.failure_id,
            expected_control_version=payload.expected_control_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission veya recovery görevi bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)[:500]) from exc
    except (MissionCheckpointIntegrityError, MissionEventIntegrityError, ExecutionReceiptIntegrityError) as exc:
        raise HTTPException(status_code=409, detail="Mission bütünlüğü doğrulanamadı.") from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/archive",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def archive_supervisor_command(command_id: str) -> SupervisorCommand:
    try:
        return await app.state.supervisor.archive(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete(
    "/v1/supervisor/commands/{command_id}",
    tags=["supervisor"],
)
async def delete_supervisor_command(command_id: str) -> dict[str, bool]:
    try:
        return {"deleted": await app.state.supervisor.delete(command_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/decisions/{decision_id}",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def answer_supervisor_decision(
    command_id: str,
    decision_id: str,
    request: SupervisorDecisionRequest,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.answer_decision(
            command_id=command_id,
            decision_id=decision_id,
            answer=request.answer,
            replan_when_complete=request.replan_when_complete,
            background=request.background,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/v1/supervisor/commands/{command_id}/diagnostics",
    response_class=PlainTextResponse,
    tags=["supervisor"],
)
async def read_supervisor_diagnostics(
    command_id: str,
) -> PlainTextResponse:
    try:
        command = await app.state.supervisor.get(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(
        build_command_diagnostics(command, adam_version="0.8.0")
    )


@app.get(
    "/v1/supervisor/commands/{command_id}/stream",
    tags=["supervisor"],
)
async def stream_supervisor_command_logs(command_id: str, follow: bool = False):
    async def log_generator():
        try:
            sent_sequence = 0
            while True:
                command = await app.state.supervisor.get(command_id)
                fresh_events = [
                    event for event in command.events
                    if event.sequence > sent_sequence
                ]
                for event in fresh_events:
                    sent_sequence = max(sent_sequence, event.sequence)
                    payload = {
                        "type": event.type,
                        "message": event.message,
                        "task_id": event.task_id,
                        "sequence": event.sequence,
                        "created_at": event.created_at,
                    }
                    yield "data: " + json.dumps(
                        payload, ensure_ascii=False
                    ) + "\n\n"

                if not follow:
                    diag = build_command_diagnostics(
                        command, adam_version="0.8.0"
                    )
                    yield "data: " + json.dumps(
                        {"type": "diagnostics", "message": diag},
                        ensure_ascii=False,
                    ) + "\n\n"
                    yield "data: [END_OF_STREAM]\n\n"
                    return

                if command.status in {"completed", "failed"}:
                    message = (
                        "Görev tamamlandı."
                        if command.status == "completed"
                        else "Görev durdu; ayrıntılar görev kartında."
                    )
                    yield "data: " + json.dumps(
                        {"type": "stream_closed", "message": message},
                        ensure_ascii=False,
                    ) + "\n\n"
                    return

                yield "data: " + json.dumps(
                    {
                        "type": "heartbeat",
                        "message": command.operation_message
                        or "Prometheus çalışıyor; yeni olay bekleniyor.",
                        "route": command.operation_route,
                        "status": command.status,
                    },
                    ensure_ascii=False,
                ) + "\n\n"
                await asyncio.sleep(2.0)
        except Exception as exc:
            yield "data: " + json.dumps(
                {"type": "stream_error", "message": f"Log akış hatası: {exc}"},
                ensure_ascii=False,
            ) + "\n\n"

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@app.post(
    "/v1/supervisor/commands/{command_id}/retry-planning",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def retry_supervisor_planning(
    command_id: str,
    background: bool = True,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.retry_planning(
            command_id=command_id,
            background=background,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/advance",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def advance_supervisor_command(
    command_id: str,
    request: SupervisorAdvanceRequest,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.advance(
            command_id=command_id,
            max_tasks=request.max_tasks,
            background=request.background,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/tasks/{task_id}/run",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def run_supervisor_task(
    command_id: str,
    task_id: str,
    background: bool = False,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.run_task(
            command_id=command_id,
            task_id=task_id,
            background=background,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/tasks/{task_id}/approve",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def approve_supervisor_task(
    command_id: str,
    task_id: str,
    request: SupervisorApprovalRequest | None = None,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.approve(
            command_id=command_id,
            task_id=task_id,
            expected_approval_id=(
                request.approval_id if request else None
            ),
            expected_approval_version=(
                request.approval_version if request else None
            ),
            background=(request.background if request else None),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/supervisor/commands/{command_id}/tasks/{task_id}/reject",
    response_model=SupervisorCommand,
    tags=["supervisor"],
)
async def reject_supervisor_task(
    command_id: str,
    task_id: str,
    request: SupervisorApprovalRequest | None = None,
) -> SupervisorCommand:
    try:
        return await app.state.supervisor.reject(
            command_id=command_id,
            task_id=task_id,
            expected_approval_id=(
                request.approval_id if request else None
            ),
            expected_approval_version=(
                request.approval_version if request else None
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/v1/planning/validate",
    response_model=PlanningValidateResponse,
    tags=["planning"],
)
async def validate_plan(
    request: PlanningValidateRequest,
) -> PlanningValidateResponse:
    try:
        document = parse_planning_document(
            request.text,
            max_tasks=app.state.settings.planning_max_tasks,
        )
    except PlanningParseError as exc:
        return PlanningValidateResponse(
            valid=False,
            errors=[str(exc)],
        )

    tree = await app.state.tools.execute(
        "workspace_list",
        {
            "path": ".",
            "depth": 8,
            "max_entries": 500,
        },
    )
    known_paths = {
        str(item["path"])
        for item in tree.get("entries", [])
        if item.get("type") == "file" and item.get("path")
    }
    result = validate_planning_document(
        document,
        known_paths=known_paths,
        known_agents=set(app.state.agents.ids()),
    )

    return PlanningValidateResponse(
        valid=result.valid,
        errors=result.errors,
        warnings=result.warnings,
        execution_layers=result.execution_layers,
        tasks=[
            PlanningTaskPreview(
                id=task.id,
                title=task.title,
                priority=task.priority,
                assigned_agent=task.assigned_agent,
                evidence=[
                    PlanningEvidencePreview(
                        type=evidence.type,
                        value=evidence.value,
                    )
                    for evidence in task.evidence
                ],
                dependencies=task.dependencies,
                parallelizable=task.parallelizable,
                user_approval=task.user_approval,
            )
            for task in document.tasks
        ],
    )


@app.post(
    "/v1/routing/preview",
    response_model=RoutingPreviewResponse,
    tags=["orchestration"],
)
async def routing_preview(
    request: RoutingPreviewRequest,
) -> RoutingPreviewResponse:
    from app.core.schemas import ChatMessage

    orchestrator: Orchestrator = app.state.orchestrator
    task_type, scores = await orchestrator.preview_scores(
        messages=[ChatMessage(role="user", content=request.message)]
    )
    return RoutingPreviewResponse(task_type=task_type, scores=scores)


@app.post(
    "/v1/orchestrate",
    response_model=OrchestrateResponse,
    tags=["orchestration"],
)
async def orchestrate(request: OrchestrateRequest) -> OrchestrateResponse:
    orchestrator: Orchestrator = app.state.orchestrator
    try:
        return await orchestrator.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Beklenmeyen sunucu hatası.",
        ) from exc


@app.get(
    "/v1/operations",
    response_model=OperationsStatusResponse,
    tags=["system"],
)
async def operations() -> OperationsStatusResponse:
    settings = app.state.settings
    store: OperationsStore = app.state.store
    orchestrator: Orchestrator = app.state.orchestrator
    catalog: RouteCatalog = app.state.catalog

    stats_by_route = {
        row["route_key"]: row
        for row in await store.route_stats()
    }
    route_rows: list[RouteUsage] = []

    for route in catalog.all():
        used = await store.route_requests_today(route.key)
        budget = settings.daily_budget_for_route(route.key)
        remaining = None if budget == 0 else max(0, budget - used)
        stats = stats_by_route.get(route.key, {})
        circuit = await orchestrator.circuit_breaker.status(route.key)
        route_rows.append(
            RouteUsage(
                route_key=route.key,
                provider=route.provider,
                model=route.model,
                label=route.label,
                requests_today=used,
                daily_budget=budget,
                remaining_today=remaining,
                total_calls=int(stats.get("total_calls", 0)),
                successful_calls=int(stats.get("successful_calls", 0)),
                failed_calls=int(stats.get("failed_calls", 0)),
                average_latency_ms=int(stats.get("average_latency_ms", 0)),
                input_tokens=int(stats.get("total_input_tokens", 0)),
                output_tokens=int(stats.get("total_output_tokens", 0)),
                circuit_open=bool(circuit["open"]),
                circuit_retry_after_seconds=int(
                    circuit["retry_after_seconds"]
                ),
                remote_request_limit=stats.get("remote_request_limit"),
                remote_requests_remaining=stats.get(
                    "remote_requests_remaining"
                ),
            )
        )

    return OperationsStatusResponse(
        date_utc=datetime.now(timezone.utc).date().isoformat(),
        routes=route_rows,
        verify_requests_today=await store.mode_requests_today("verify"),
        verify_daily_budget=settings.verify_daily_budget,
        cache_entries=await store.cache_count(),
    )


@app.delete("/v1/cache", tags=["system"])
async def clear_cache() -> dict[str, int]:
    return {"deleted": await app.state.store.clear_cache()}
