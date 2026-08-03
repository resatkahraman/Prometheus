from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Role = Literal["system", "user", "assistant"]
AutonomyMode = Literal["locked", "task", "trusted"]
Mode = Literal["economy", "auto", "direct", "verify", "council"]
TaskType = Literal[
    "coding",
    "summarization",
    "translation",
    "reasoning",
    "general",
]


class ChatMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1)


class OrchestrateRequest(BaseModel):
    message: str | None = Field(default=None, min_length=1)
    messages: list[ChatMessage] | None = None
    mode: Mode = "auto"
    provider: str | None = None
    providers: list[str] | None = None
    preferred_routes: list[str] | None = None
    excluded_routes: list[str] | None = None
    task_type_override: TaskType | None = None
    system_prompt: str = (
        "Kullanıcıya doğru, uygulanabilir ve açık bir cevap ver. "
        "Bilmediğin bilgileri uydurma; belirsizlikleri belirt."
    )
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_output_tokens: int | None = Field(default=None, ge=64, le=16_384)
    include_candidates: bool = False
    bypass_cache: bool = False
    usage_scope: str | None = Field(default=None, max_length=128)
    usage_task_id: str | None = Field(default=None, max_length=128)
    task_signature: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{20}$",
    )

    @model_validator(mode="after")
    def validate_input(self):
        if bool(self.message) == bool(self.messages):
            raise ValueError(
                "Tam olarak bir giriş biçimi kullan: 'message' veya 'messages'."
            )
        if self.mode == "direct" and not self.provider:
            raise ValueError("direct modunda 'provider' route anahtarı zorunludur.")
        return self

    def normalized_messages(self) -> list[ChatMessage]:
        if self.messages is not None:
            return self.messages
        return [ChatMessage(role="user", content=self.message or "")]


class CandidateResponse(BaseModel):
    route_key: str
    provider: str
    model: str
    content: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class FailedProvider(BaseModel):
    route_key: str
    provider: str
    error: str


class RouteScore(BaseModel):
    route_key: str
    provider: str
    model: str
    score: float
    eligible: bool
    reasons: list[str]


class OrchestrateResponse(BaseModel):
    answer: str
    mode: Mode
    selected_route: str
    selected_provider: str
    model: str
    finish_reason: str | None = None
    latency_ms: int
    task_type: TaskType
    route_reason: str
    calls_used: int = 0
    cache_hit: bool = False
    routing_scores: list[RouteScore] = Field(default_factory=list)
    candidates: list[CandidateResponse] | None = None
    failures: list[FailedProvider] = Field(default_factory=list)


class ProviderInfo(BaseModel):
    name: str
    enabled: bool
    model: str | None = None


class RouteInfo(BaseModel):
    route_key: str
    provider: str
    model: str
    enabled: bool
    label: str


class HealthResponse(BaseModel):
    status: str
    providers: list[ProviderInfo]
    routes: list[RouteInfo]
    tools: list[str]
    agents: list[str]
    workspace_root: str
    paid_models_enabled: bool


class CatalogModel(BaseModel):
    id: str
    name: str | None = None
    publisher: str | None = None
    rate_limit_tier: str | None = None


class ModelCatalogResponse(BaseModel):
    provider: str
    models: list[CatalogModel]


class RouteUsage(BaseModel):
    route_key: str
    provider: str
    model: str
    label: str
    requests_today: int
    daily_budget: int
    remaining_today: int | None
    total_calls: int
    successful_calls: int
    failed_calls: int
    average_latency_ms: int
    input_tokens: int
    output_tokens: int
    circuit_open: bool
    circuit_retry_after_seconds: int
    remote_request_limit: int | None = None
    remote_requests_remaining: int | None = None


class OperationsStatusResponse(BaseModel):
    date_utc: str
    routes: list[RouteUsage]
    verify_requests_today: int
    verify_daily_budget: int
    cache_entries: int


class RoutingPreviewRequest(BaseModel):
    message: str = Field(min_length=1)


class RoutingPreviewResponse(BaseModel):
    task_type: TaskType
    scores: list[RouteScore]


AgentRoutingMode = Literal["auto", "economy", "direct"]


class AgentRequest(BaseModel):
    message: str | None = Field(default=None, min_length=1)
    messages: list[ChatMessage] | None = None
    agent_id: str = Field(default="worker", pattern=r"^[a-z][a-z0-9_]{1,39}$")
    routing_mode: AgentRoutingMode = "auto"
    provider: str | None = None
    max_steps: int | None = Field(default=None, ge=1, le=40)
    max_model_calls: int | None = Field(default=None, ge=1, le=50)
    supervised_budget: bool = False
    include_trace: bool = True
    allow_deterministic_tools: bool = True
    additional_write_paths: list[str] = Field(default_factory=list)
    exclusive_write_paths: list[str] = Field(default_factory=list)
    source_evidence_pending_paths: list[str] = Field(
        default_factory=list
    )
    applied_tool_fingerprints: list[str] = Field(default_factory=list)
    disable_auto_context: bool = False
    max_output_tokens: int | None = Field(default=None, ge=128, le=16_384)
    response_protocol: Literal["json", "single_file", "single_patch"] = "json"
    single_file_path: str | None = None
    single_file_base_content: str | None = None
    single_file_base_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    preferred_routes: list[str] | None = None
    excluded_routes: list[str] | None = None
    usage_scope: str | None = Field(default=None, max_length=128)
    usage_task_id: str | None = Field(default=None, max_length=128)
    task_signature: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{20}$",
    )

    @model_validator(mode="after")
    def validate_agent_input(self):
        if bool(self.message) == bool(self.messages):
            raise ValueError(
                "Tam olarak bir giriş biçimi kullan: 'message' veya 'messages'."
            )
        if self.routing_mode == "direct" and not self.provider:
            raise ValueError(
                "Agent direct routing modunda 'provider' route anahtarı zorunludur."
            )
        if self.response_protocol in {"single_file", "single_patch"}:
            if not isinstance(self.single_file_path, str) or not self.single_file_path.strip():
                raise ValueError(
                    "single_file protokolünde 'single_file_path' zorunludur."
                )
            if self.exclusive_write_paths and self.single_file_path not in self.exclusive_write_paths:
                raise ValueError(
                    "single_file_path, exclusive_write_paths sözleşmesinin içinde olmalıdır."
                )
        if self.response_protocol == "single_patch":
            if self.single_file_base_content is None:
                raise ValueError(
                    "single_patch protokolünde taban dosya içeriği zorunludur."
                )
            import hashlib

            actual_sha256 = hashlib.sha256(
                self.single_file_base_content.encode("utf-8")
            ).hexdigest()
            if actual_sha256 != self.single_file_base_sha256:
                raise ValueError(
                    "single_patch taban içeriği ile sha256 değeri uyuşmuyor."
                )
        return self

    def normalized_messages(self) -> list[ChatMessage]:
        if self.messages is not None:
            return self.messages
        return [ChatMessage(role="user", content=self.message or "")]


class AgentStep(BaseModel):
    step: int
    selected_route: str
    provider: str
    model: str
    action: str
    reason: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    tool_result: Any | None = None
    latency_ms: int
    raw_output: str | None = None


class ApprovalInfo(BaseModel):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    description: str
    preview: dict[str, Any]
    created_at: str
    expires_at: str


class AgentResponse(BaseModel):
    answer: str
    agent_id: str
    agent_name: str
    status: Literal[
        "completed",
        "max_steps",
        "failed",
        "awaiting_approval",
    ]
    steps_used: int
    model_calls_used: int
    tools_used: list[str]
    final_route: str | None = None
    final_provider: str | None = None
    final_model: str | None = None
    routing_scores: list[RouteScore] = Field(default_factory=list)
    trace: list[AgentStep] | None = None
    session_id: str | None = None
    pending_approval: ApprovalInfo | None = None


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    risk_level: str
    requires_approval: bool


class WorkspaceStatus(BaseModel):
    root: str
    exists: bool
    project_types: list[str]
    git_repository: bool
    paid_models_enabled: bool



class PlanningValidateRequest(BaseModel):
    text: str = Field(min_length=1)


class PlanningEvidencePreview(BaseModel):
    type: str
    value: str


class PlanningTaskPreview(BaseModel):
    id: str
    title: str
    priority: str
    assigned_agent: str
    evidence: list[PlanningEvidencePreview]
    dependencies: list[str]
    parallelizable: str
    user_approval: str


class PlanningValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_layers: list[list[str]] = Field(default_factory=list)
    tasks: list[PlanningTaskPreview] = Field(default_factory=list)



class SupervisorCreateRequest(BaseModel):
    goal: str = Field(min_length=3)
    routing_mode: AgentRoutingMode = "auto"
    provider: str | None = None
    auto_start: bool = False
    background: bool = True
    autonomy_mode: AutonomyMode = "task"

    @model_validator(mode="after")
    def validate_supervisor_provider(self):
        if self.routing_mode == "direct" and not self.provider:
            raise ValueError(
                "Supervisor direct routing modunda provider zorunludur."
            )
        return self


class SupervisorDecisionRequest(BaseModel):
    answer: str = Field(min_length=1)
    replan_when_complete: bool = True
    background: bool = False


class SupervisorAdvanceRequest(BaseModel):
    max_tasks: int = Field(default=1, ge=1, le=10)
    background: bool = False


class SupervisorApprovalRequest(BaseModel):
    approval_id: str | None = None
    approval_version: int | None = Field(default=None, ge=1)
    background: bool = True


class ProjectRunPreviewRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)
    workspace_path: str = Field(default=".", max_length=1000)

    @model_validator(mode="after")
    def validate_preview_fields(self):
        stripped_goal = self.goal.strip()
        if not stripped_goal or len(stripped_goal) < 3:
            raise ValueError("Görev açıklaması boş olamaz ve en az 3 karakter olmalıdır.")
        self.goal = stripped_goal
        
        stripped_path = self.workspace_path.strip() if self.workspace_path else "."
        if not stripped_path:
            stripped_path = "."
        self.workspace_path = stripped_path
        return self


class ProjectRunPreviewTask(BaseModel):
    title: str
    assigned_agent: str
    exact_files: list[str] = Field(default_factory=list)
    verification: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class ProjectRunPreviewResponse(BaseModel):
    goal: str
    workspace_path: str
    tasks: list[ProjectRunPreviewTask]
    exact_files: list[str]
    verification_commands: list[str]
    warnings: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    model_calls: int = 0
    total_tokens: int = 0
    side_effect_free: bool = True
    preview_digest: str = ""


class ProjectRunCommitRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)
    workspace_path: str = Field(default=".", max_length=1000)
    preview_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    autonomy_mode: AutonomyMode = "task"
    background: bool = True
    force_new: bool = False

    @model_validator(mode="after")
    def validate_commit_fields(self):
        stripped_goal = self.goal.strip()
        if not stripped_goal or len(stripped_goal) < 3:
            raise ValueError("Görev açıklaması boş olamaz ve en az 3 karakter olmalıdır.")
        self.goal = stripped_goal

        stripped_path = self.workspace_path.strip() if self.workspace_path else "."
        if not stripped_path:
            stripped_path = "."
        self.workspace_path = stripped_path
        return self


class ProjectRunCommitResponse(BaseModel):
    command_id: str
    status: str
    goal: str
    workspace_path: str
    preview_digest: str
    task_ids: list[str]
    approval_ids: list[str]
    requires_approval: bool = True
    model_calls: int = 0
    total_tokens: int = 0
    execution_started: bool = False
    created: bool


class RunFileChange(BaseModel):
    relative_path: str
    change_type: Literal["unchanged", "added", "modified", "deleted"]
    existed_before: bool
    exists_after: bool
    sha256_before: str | None = None
    sha256_after: str | None = None
    size_before: int | None = None
    size_after: int | None = None
    text_diff_preview: str | None = None
    revertable: bool
    revert_block_reason: str | None = None


class RunChangeReviewResponse(BaseModel):
    command_id: str
    status: str
    terminal: bool
    changed_files: list[RunFileChange]
    changed_file_count: int
    verification_summary: list[dict[str, Any]] = Field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    delivery_summary: str | None = None
    can_revert: bool
    revert_confirmation: str


class RunRevertRequest(BaseModel):
    confirmation: str


class RunRevertResponse(BaseModel):
    command_id: str
    reverted: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    event_recorded: bool = True


class WorkspaceProjectGitStatus(BaseModel):
    is_repository: bool = False
    git_root: str | None = None
    branch: str | None = None
    dirty: bool = False
    changed_file_count: int = 0
    ahead: int | None = None
    behind: int | None = None


class WorkspaceProjectSummary(BaseModel):
    name: str
    workspace_path: str
    project_types: list[str] = Field(default_factory=list)
    manifests: list[str] = Field(default_factory=list)
    suggested_verifications: list[str] = Field(default_factory=list)
    git: WorkspaceProjectGitStatus = Field(default_factory=WorkspaceProjectGitStatus)
    recent_rank: int | None = None


class WorkspaceProjectsResponse(BaseModel):
    workspace_root_name: str
    projects: list[WorkspaceProjectSummary] = Field(default_factory=list)
    total: int = 0
    scan_depth: int = 2
    truncated: bool = False


class WorkspaceProjectSelectRequest(BaseModel):
    workspace_path: str


class WorkspaceProjectSelectResponse(BaseModel):
    project: WorkspaceProjectSummary
    selected: bool = True




