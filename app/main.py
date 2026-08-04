import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

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
    ProjectRunHistoryResponse,
    ProjectRunRetryRequest,
    ProjectRunRetryResponse,
)
from app.workspace.projects import WorkspaceProjectManager
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.routes import RouteCatalog
from app.providers.registry import ProviderRegistry
from app.planning.integrity import validate_planning_document
from app.planning.parser import PlanningParseError, parse_planning_document
from app.storage.operations import OperationsStore
from app.supervisor.diagnostics import build_command_diagnostics
from app.supervisor.models import SupervisorCommand, SupervisorCommandSummary
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
    PandoraSessionManager,
    request_pandora_session_token,
)
from app.supervisor.service import SupervisorService
from app.tools.base import ToolError
from app.tools.registry import build_default_tool_registry
from app.workspace.policy import WorkspacePolicy
from app.branding import BRAND_NAME, BRAND_STAGE, BRAND_VERSION


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
    tools = build_default_tool_registry(
        settings=settings,
        approvals=approvals,
    )
    agents = build_default_agent_registry(tools.names())
    agent = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=tools,
        agents=agents,
    )
    supervisor = SupervisorService(
        settings=settings,
        agent=agent,
        agents=agents,
        tools=tools,
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
    app.state.supervisor = supervisor
    app.state.workspace_projects = WorkspaceProjectManager(settings.workspace_root)
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
    "cihaz özelliklerine eriştiğini iddia etme. Böyle bir işlem istenirse "
    "bu mobil sohbet sürümünde desteklenmediğini açıkça belirt. Sistem, "
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

    if request.state.pandora_session is None:
        raise HTTPException(
            status_code=401,
            detail=PANDORA_PAIRING_REQUIRED_DETAIL,
        )

    try:
        session = manager.begin_chat_request(token)
    except PandoraChatBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail=PANDORA_CHAT_BUSY_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except PandoraChatRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=PANDORA_CHAT_RATE_LIMIT_DETAIL,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    if session is None:
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

        response.headers["Cache-Control"] = "no-store"
        return PandoraChatResponse(answer=answer)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=PANDORA_CHAT_UNAVAILABLE_DETAIL,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=PANDORA_CHAT_UNAVAILABLE_DETAIL,
        ) from exc
    finally:
        manager.end_chat_request(token)


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
        workspace_root=str(settings.workspace_root.expanduser().resolve()),
        paid_models_enabled=settings.effective_paid_models_enabled,
    )


@app.get("/v1/workspace", response_model=WorkspaceStatus, tags=["workspace"])
async def workspace_status() -> WorkspaceStatus:
    settings = app.state.settings
    summary = await app.state.tools.execute("project_summary", {})
    return WorkspaceStatus(
        root=str(settings.workspace_root.expanduser().resolve()),
        exists=settings.workspace_root.expanduser().resolve().exists(),
        project_types=summary["project_types"],
        git_repository=summary["git_repository"],
        paid_models_enabled=settings.effective_paid_models_enabled,
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
async def list_workspace_projects() -> WorkspaceProjectsResponse:
    try:
        manager: WorkspaceProjectManager = app.state.workspace_projects
        return manager.list_projects()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/v1/workspace/projects/select",
    response_model=WorkspaceProjectSelectResponse,
    tags=["workspace"],
)
async def select_workspace_project(
    payload: WorkspaceProjectSelectRequest,
) -> WorkspaceProjectSelectResponse:
    try:
        manager: WorkspaceProjectManager = app.state.workspace_projects
        return manager.select_project(payload.workspace_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
