from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    project_run_preview_digest: str | None = None
    project_run_workspace_path: str | None = None

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


class MissionEventRecord(BaseModel):
    schema_version: int = 1
    event_id: str
    mission_id: str
    sequence: int
    event_type: str
    canonical_kind: Literal[
        "mission",
        "plan",
        "step",
        "tool",
        "approval",
        "checkpoint",
        "recovery",
        "system",
    ]
    occurred_at: datetime
    task_id: str | None = None
    approval_id: str | None = None
    actor: str = "supervisor"
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str

    @model_validator(mode="after")
    def validate_mission_event(self) -> "MissionEventRecord":
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if not self.event_id or len(self.event_id.strip()) == 0 or len(self.event_id) > 128:
            raise ValueError("event_id must be non-empty and <= 128 chars")
        if not self.mission_id or len(self.mission_id.strip()) == 0 or len(self.mission_id) > 200:
            raise ValueError("mission_id must be non-empty and <= 200 chars")
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if not self.event_type or len(self.event_type.strip()) == 0 or len(self.event_type) > 160:
            raise ValueError("event_type must be non-empty and <= 160 chars")
        if not self.actor or len(self.actor.strip()) == 0 or len(self.actor) > 80:
            raise ValueError("actor must be non-empty and <= 80 chars")

        if not self.event_hash.startswith("sha256:") or len(self.event_hash) != 71:
            raise ValueError("event_hash must be exact sha256:<64 hex>")

        if self.previous_hash is not None:
            if not self.previous_hash.startswith("sha256:") or len(self.previous_hash) != 71:
                raise ValueError("previous_hash must be sha256:<64 hex>")

        if self.sequence == 1 and self.previous_hash is not None:
            raise ValueError("sequence 1 must have previous_hash=None")

        if self.sequence > 1 and self.previous_hash is None:
            raise ValueError("sequence > 1 must have previous_hash")

        return self


class MissionEventPage(BaseModel):
    mission_id: str
    events: list[MissionEventRecord]
    count: int
    after_sequence: int
    next_after_sequence: int | None = None
    has_more: bool = False
    source: Literal["journal", "legacy_command_events", "empty"]
    integrity_verified: bool
    last_sequence: int
    last_event_hash: str | None = None


class MissionEventIntegrity(BaseModel):
    mission_id: str
    valid: bool
    event_count: int
    last_sequence: int
    last_event_hash: str | None = None
    error_code: str | None = None
    error_sequence: int | None = None


class MissionStateProjection(BaseModel):
    mission_id: str
    event_count: int
    last_sequence: int
    last_event_type: str | None = None
    command_status: str | None = None
    task_statuses: dict[str, str] = Field(default_factory=dict)
    pending_approval_ids: list[str] = Field(default_factory=list)
    terminal: bool = False


class ExecutionReceipt(BaseModel):
    schema_version: int = 1
    receipt_id: str
    mission_id: str
    sequence: int

    execution_kind: Literal["tool", "worker", "verification", "command"]
    actor_kind: Literal["supervisor", "worker", "tool", "system"]
    actor_id: str
    tool_name: str | None = None
    worker_role: str | None = None

    task_id: str | None = None
    step_id: str | None = None
    approval_id: str | None = None
    sandbox_id: str | None = None

    started_at: datetime
    completed_at: datetime
    duration_ms: int
    outcome: Literal["succeeded", "failed", "cancelled", "timed_out"]

    request_summary: str
    input_hash: str
    result_hash: str

    capabilities: list[str] = Field(default_factory=list)
    filesystem_scope: list[str] = Field(default_factory=list)
    network_access: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    affected_files: list[str] = Field(default_factory=list)

    stdout_preview: str | None = None
    stderr_preview: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)

    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    previous_receipt_hash: str | None = None
    receipt_hash: str

    @model_validator(mode="after")
    def validate_receipt(self) -> "ExecutionReceipt":
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be before started_at")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")

        self.receipt_id = self.receipt_id.strip()[:100]
        self.mission_id = self.mission_id.strip()[:100]
        self.actor_id = self.actor_id.strip()[:100]
        if self.tool_name:
            self.tool_name = self.tool_name.strip()[:100]
        if self.worker_role:
            self.worker_role = self.worker_role.strip()[:100]
        if self.task_id:
            self.task_id = self.task_id.strip()[:100]
        if self.step_id:
            self.step_id = self.step_id.strip()[:100]
        if self.approval_id:
            self.approval_id = self.approval_id.strip()[:100]
        if self.sandbox_id:
            self.sandbox_id = self.sandbox_id.strip()[:100]
        if self.error_code:
            self.error_code = self.error_code.strip()[:100]

        if self.execution_kind == "tool" and not self.tool_name:
            raise ValueError("tool_name is required for tool execution")
        if self.execution_kind == "worker" and not self.worker_role:
            raise ValueError("worker_role is required for worker execution")

        if self.sequence == 1 and self.previous_receipt_hash is not None:
            raise ValueError("previous_receipt_hash must be None for sequence 1")
        if self.sequence > 1 and self.previous_receipt_hash is None:
            raise ValueError("previous_receipt_hash is required for sequence > 1")

        for name, hval in [
            ("input_hash", self.input_hash),
            ("result_hash", self.result_hash),
            ("receipt_hash", self.receipt_hash),
        ]:
            if not hval.startswith("sha256:") or len(hval) != 71 or not all(c in "0123456789abcdef" for c in hval[7:]):
                raise ValueError(f"{name} must be in sha256:<64 hex> format")

        if self.previous_receipt_hash:
            ph = self.previous_receipt_hash
            if not ph.startswith("sha256:") or len(ph) != 71 or not all(c in "0123456789abcdef" for c in ph[7:]):
                raise ValueError("previous_receipt_hash must be in sha256:<64 hex> format")

        if len(self.request_summary) > 4000:
            self.request_summary = self.request_summary[:3985] + "...[TRUNCATED]"
        if self.stdout_preview and len(self.stdout_preview) > 20000:
            self.stdout_preview = self.stdout_preview[:19985] + "...[TRUNCATED]"
        if self.stderr_preview and len(self.stderr_preview) > 20000:
            self.stderr_preview = self.stderr_preview[:19985] + "...[TRUNCATED]"
        if self.error_message and len(self.error_message) > 20000:
            self.error_message = self.error_message[:19985] + "...[TRUNCATED]"

        def _clean_list(items: list[str], max_len: int = 500) -> list[str]:
            seen = set()
            res = []
            for item in items:
                cleaned = str(item).strip()[:200]
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    res.append(cleaned)
                    if len(res) >= max_len:
                        break
            return res

        self.capabilities = _clean_list(self.capabilities, 200)
        self.filesystem_scope = _clean_list(self.filesystem_scope, 500)
        self.network_access = _clean_list(self.network_access, 200)
        self.affected_files = _clean_list(self.affected_files, 500)
        self.artifact_ids = _clean_list(self.artifact_ids, 500)

        return self


class ExecutionReceiptPage(BaseModel):
    mission_id: str
    receipts: list[ExecutionReceipt]
    count: int
    after_sequence: int
    next_after_sequence: int | None = None
    has_more: bool = False
    source: Literal["receipt_store", "empty"]
    integrity_verified: bool
    last_sequence: int
    last_receipt_hash: str | None = None


class ExecutionReceiptIntegrity(BaseModel):
    mission_id: str
    valid: bool
    receipt_count: int
    last_sequence: int
    last_receipt_hash: str | None = None
    error_code: str | None = None
    error_sequence: int | None = None


class ExecutionReceiptSummary(BaseModel):
    receipt_id: str
    mission_id: str
    sequence: int
    execution_kind: str
    actor_id: str
    task_id: str | None = None
    outcome: str
    duration_ms: int
    affected_file_count: int
    artifact_count: int
    receipt_hash: str

