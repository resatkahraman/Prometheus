from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.schemas import AgentResponse


AutonomyMode = Literal["locked", "task", "trusted"]


CommandStatus = Literal[
    "planning",
    "waiting_decision",
    "ready",
    "running",
    "awaiting_approval",
    "reviewing",
    "completed",
    "failed",
]

TaskCommandStatus = Literal[
    "blocked",
    "ready",
    "running",
    "awaiting_approval",
    "reviewing",
    "rework_required",
    "completed",
    "failed",
]

DecisionStatus = Literal["pending", "answered"]
ApprovalState = Literal[
    "idle",
    "pending",
    "processing",
    "applied",
    "rejected",
    "failed",
]

HandoffType = Literal[
    "task_assignment",
    "completion",
    "review_request",
    "review_accept",
    "review_reject",
    "rework",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupervisorDecision(BaseModel):
    id: str
    question: str
    status: DecisionStatus = "pending"
    answer: str | None = None
    auto_resolved: bool = False
    source_decision_id: str | None = None


class SupervisorHandoff(BaseModel):
    id: str
    task_id: str
    type: HandoffType
    from_agent: str
    to_agent: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class SupervisorEvent(BaseModel):
    sequence: int
    type: str
    message: str
    task_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class SupervisorApprovalRecord(BaseModel):
    version: int
    approval_id: str
    state: ApprovalState
    phase: Literal["worker", "reviewer"]
    tool: str | None = None
    description: str | None = None
    preview: dict[str, Any] | None = None
    arguments: dict[str, Any] | None = None
    fingerprint: str | None = None
    requested_at: str = Field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    success: bool | None = None
    result: Any | None = None


class SupervisorFailureRecord(BaseModel):
    signature: str
    kind: str
    summary: str
    count: int = 1
    strategy_key: str | None = None
    exit_code: int | None = None
    created_at: str = Field(default_factory=utc_now)


class SupervisorTask(BaseModel):
    id: str
    title: str
    priority: str
    assigned_agent: str
    evidence: list[dict[str, str]]
    acceptance_criteria: list[str]
    dependencies: list[str]
    dependency_reason: str
    parallelizable: str
    verification: str
    user_approval: str
    exact_files: list[str]

    status: TaskCommandStatus = "blocked"
    attempts: int = 0
    continuation_resumes: int = 0
    recovery_reason: str | None = None
    reconciliation_missing_files: list[str] = Field(
        default_factory=list
    )
    reconciliation_verification_found: bool = False
    reconciliation_last_checked_at: str | None = None
    materialized_files: list[str] = Field(default_factory=list)
    workspace_state_validated: bool = False
    effective_verification: str | None = None
    verification_strategy: str | None = None
    successful_verification_version: int | None = None
    verification_failures: int = 0
    local_model_attempts: int = 0
    task_signature: str | None = None
    recalled_strategy_ids: list[str] = Field(default_factory=list)
    recalled_orientation_ids: list[str] = Field(default_factory=list)
    last_generation_route: str | None = None
    last_generation_model: str | None = None
    environment_revision: int = 0
    last_environment_change_version: int = 0
    terminal_runtime_revision: str | None = None
    focused_generation_revision: str | None = None
    blocked_state_token: str | None = None
    autonomy_granted: bool = False
    failure_counts: dict[str, int] = Field(default_factory=dict)
    failure_state_tokens: dict[str, str] = Field(
        default_factory=dict
    )
    failure_history: list[SupervisorFailureRecord] = Field(default_factory=list)
    attempted_strategies: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    last_answer: str | None = None
    review_answer: str | None = None
    agent_session_id: str | None = None
    approval_id: str | None = None
    approval_phase: Literal["worker", "reviewer"] | None = None
    approval_version: int = 0
    approval_state: ApprovalState = "idle"
    approval_tool: str | None = None
    approval_description: str | None = None
    approval_preview: dict[str, Any] | None = None
    approval_expires_at: str | None = None
    processing_approval_id: str | None = None
    last_consumed_approval_id: str | None = None
    last_approval_message: str | None = None
    approval_history: list[SupervisorApprovalRecord] = Field(
        default_factory=list
    )
    last_agent_response: AgentResponse | None = None


class SupervisorCommand(BaseModel):
    id: str
    goal: str
    status: CommandStatus
    autonomy_mode: AutonomyMode = "task"
    auto_run: bool = False
    plan_text: str
    tasks: list[SupervisorTask]
    decisions: list[SupervisorDecision] = Field(default_factory=list)
    decision_history: list[SupervisorDecision] = Field(default_factory=list)
    execution_layers: list[list[str]] = Field(default_factory=list)
    handoffs: list[SupervisorHandoff] = Field(default_factory=list)
    events: list[SupervisorEvent] = Field(default_factory=list)
    planning_agent_response: AgentResponse | None = None
    failure_reason: str | None = None
    archived: bool = False
    archived_at: str | None = None

    active_operation: str | None = None
    operation_phase: str | None = None
    operation_message: str | None = None
    operation_attempt: int = 0
    operation_max_attempts: int = 0
    operation_route: str | None = None
    operation_started_at: str | None = None
    last_heartbeat_at: str | None = None

    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class SupervisorCreateRequest(BaseModel):
    goal: str = Field(min_length=3)
    autonomy_mode: AutonomyMode = "task"
    routing_mode: Literal["auto", "economy", "direct"] = "auto"
    provider: str | None = None
    auto_start: bool = False
    background: bool = False
    force_new: bool = False


class SupervisorDecisionRequest(BaseModel):
    answer: str = Field(min_length=1)
    replan_when_complete: bool = True
    background: bool = False


class SupervisorAdvanceRequest(BaseModel):
    max_tasks: int = Field(default=1, ge=1, le=10)
    background: bool = False


class SupervisorCommandSummary(BaseModel):
    id: str
    goal: str
    status: CommandStatus
    autonomy_mode: AutonomyMode = "task"
    auto_run: bool = False
    completed_tasks: int
    total_tasks: int
    pending_decisions: int
    created_at: str
    updated_at: str
