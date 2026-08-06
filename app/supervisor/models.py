from datetime import datetime, timezone
import re
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
    "paused",
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

MissionFailurePhase = Literal[
    "planning", "task_execution", "verification", "review", "approval",
    "checkpoint", "resume", "background", "unknown",
]
MissionFailureCategory = Literal[
    "transient_provider", "rate_limited", "timeout", "dependency_unavailable",
    "verification_failed", "approval_rejected", "policy_blocked",
    "state_conflict", "integrity_failure", "cancelled", "invalid_request",
    "internal_error", "unknown",
]
MissionFailureSeverity = Literal["warning", "error", "critical"]
MissionRecoveryAction = Literal[
    "retry_task", "resume_checkpoint", "request_approval", "manual_intervention", "none",
]
MissionRecoveryStatus = Literal[
    "idle", "eligible", "scheduled", "running", "recovered", "blocked", "exhausted",
]

MissionBranchWorkspaceMode = Literal["shared_current_workspace"]

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


class MissionFailureClassification(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    failure_id: str = Field(min_length=1, max_length=160)
    failure_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    mission_id: str = Field(min_length=1, max_length=160)
    task_id: str | None = Field(default=None, max_length=160)
    source_receipt_id: str | None = Field(default=None, max_length=160)
    occurred_at: datetime
    phase: MissionFailurePhase
    category: MissionFailureCategory
    severity: MissionFailureSeverity
    error_code: str = Field(min_length=1, max_length=160)
    safe_message: str = Field(min_length=1, max_length=2000)
    retryable: bool
    recoverable: bool
    recommended_action: MissionRecoveryAction
    task_attempt: int = Field(default=0, ge=0)
    mission_recovery_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalize_public_failure(self) -> "MissionFailureClassification":
        self.failure_id = self.failure_id.strip()
        self.mission_id = self.mission_id.strip()
        self.error_code = self.error_code.strip()
        self.safe_message = self.safe_message.strip()
        self.task_id = (self.task_id or "").strip() or None
        self.source_receipt_id = (self.source_receipt_id or "").strip() or None
        if not self.failure_id or not self.mission_id or not self.error_code or not self.safe_message:
            raise ValueError("failure identifiers, code, and safe_message must be non-empty")
        unsafe = self.safe_message.casefold()
        secret_assignment = re.search(
            r"(?i)\b(?:token|password|api[_-]?key|authorization|cookie|credential|"
            r"private[_-]?key|session[_-]?token)\b\s*[:=]\s*[^\s,;]+",
            self.safe_message,
        )
        if (
            "traceback (most recent call last)" in unsafe
            or secret_assignment
            or re.search(r"(?i)(?:[a-z]:\\|/(?:home|users|root|tmp)/)", self.safe_message)
        ):
            raise ValueError("safe_message contains unsafe diagnostic data")
        return self


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
    workspace_path: str = "."
    project_key: str | None = None

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

    pause_requested: bool = False
    pause_requested_at: datetime | None = None
    pause_reason: str | None = None

    paused_at: datetime | None = None
    active_checkpoint_id: str | None = None
    resume_target_status: str | None = None

    control_version: int = 0
    resume_count: int = 0

    latest_failure: MissionFailureClassification | None = None
    recovery_status: MissionRecoveryStatus = "idle"
    recovery_attempts_for_failure: int = Field(default=0, ge=0)
    recovery_count: int = Field(default=0, ge=0)
    recovery_checkpoint_id: str | None = None
    recovery_task_id: str | None = None
    recovery_started_at: datetime | None = None
    recovery_completed_at: datetime | None = None

    root_mission_id: str | None = None
    parent_mission_id: str | None = None
    source_checkpoint_id: str | None = None
    source_checkpoint_sequence: int | None = Field(default=None, ge=1)
    source_checkpoint_hash: str | None = None
    source_checkpoint_state_hash: str | None = None
    branch_depth: int = Field(default=0, ge=0, le=64)
    branch_label: str | None = Field(default=None, max_length=160)
    branch_idempotency_key_hash: str | None = None
    branch_request_fingerprint: str | None = None
    branched_at: datetime | None = None
    branch_activation_required: bool = False
    branch_activated_at: datetime | None = None
    branch_workspace_mode: MissionBranchWorkspaceMode | None = None

    @model_validator(mode="after")
    def normalize_recovery_ids(self) -> "SupervisorCommand":
        self.recovery_checkpoint_id = (self.recovery_checkpoint_id or "").strip() or None
        self.recovery_task_id = (self.recovery_task_id or "").strip() or None
        for name in ("root_mission_id", "parent_mission_id", "source_checkpoint_id", "source_checkpoint_hash", "source_checkpoint_state_hash", "branch_idempotency_key_hash", "branch_request_fingerprint"):
            value = (getattr(self, name) or "").strip() or None
            setattr(self, name, value)
        self.branch_label = (self.branch_label or "").strip()[:160] or None
        if self.parent_mission_id is None:
            if self.branch_depth != 0 or self.branch_activation_required:
                raise ValueError("root Mission cannot require branch activation or depth")
        else:
            if self.parent_mission_id == self.id:
                raise ValueError("branch cannot reference itself")
            required = (self.root_mission_id, self.source_checkpoint_id, self.source_checkpoint_hash, self.source_checkpoint_state_hash, self.branch_idempotency_key_hash, self.branch_request_fingerprint, self.branched_at, self.branch_workspace_mode)
            if any(item is None for item in required) or self.branch_depth < 1:
                raise ValueError("child branch lineage is incomplete")
        sha_fields = ("source_checkpoint_hash", "source_checkpoint_state_hash", "branch_idempotency_key_hash", "branch_request_fingerprint")
        for name in sha_fields:
            value = getattr(self, name)
            if value is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
                raise ValueError(f"{name} must be sha256:<64 lowercase hex>")
        if self.branch_label and (re.search(r"(?i)\b(?:token|password|api[_-]?key|authorization|cookie|credential|private[_-]?key|session[_-]?token)\b\s*[:=]", self.branch_label) or re.search(r"(?i)(?:[a-z]:\\|/(?:home|users|root|tmp)/)", self.branch_label) or "traceback (most recent call last)" in self.branch_label.casefold()):
            raise ValueError("branch_label contains unsafe diagnostic data")
        if self.branch_activated_at is not None and self.branch_activation_required:
            raise ValueError("activated branch cannot still require activation")
        return self


class SupervisorCreateRequest(BaseModel):
    goal: str = Field(min_length=3)
    autonomy_mode: AutonomyMode = "task"
    routing_mode: Literal["auto", "economy", "direct"] = "auto"
    provider: str | None = None
    auto_start: bool = False
    background: bool = False
    force_new: bool = False
    workspace_path: str | None = Field(default=None, min_length=1, max_length=1_000)


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
    workspace_path: str = "."


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


class MissionCheckpointRecord(BaseModel):
    schema_version: int = 1

    checkpoint_id: str
    mission_id: str
    sequence: int

    created_at: datetime
    reason: Literal[
        "manual",
        "pause_boundary",
        "pre_execution",
        "post_execution",
        "approval_boundary",
        "system",
        "branch_origin",
    ]

    status_at_checkpoint: str
    resume_target_status: str | None = None
    current_task_id: str | None = None
    pending_approval_ids: list[str] = Field(default_factory=list)

    state_version: int
    state_hash: str
    snapshot_size_bytes: int

    resumable: bool
    consumed_by_resume: bool = False

    previous_checkpoint_hash: str | None = None
    checkpoint_hash: str

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "MissionCheckpointRecord":
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if self.state_version < 0:
            raise ValueError("state_version must be >= 0")
        if self.snapshot_size_bytes < 0:
            raise ValueError("snapshot_size_bytes must be >= 0")
        if not self.checkpoint_id or not self.checkpoint_id.strip():
            raise ValueError("checkpoint_id must not be empty")
        if not self.mission_id or not self.mission_id.strip():
            raise ValueError("mission_id must not be empty")
        if not self.state_hash.startswith("sha256:") or len(self.state_hash) != 71:
            raise ValueError("state_hash must be sha256:<64 hex>")
        if not self.checkpoint_hash.startswith("sha256:") or len(self.checkpoint_hash) != 71:
            raise ValueError("checkpoint_hash must be sha256:<64 hex>")
        if self.sequence == 1 and self.previous_checkpoint_hash is not None:
            raise ValueError("sequence 1 cannot have previous_checkpoint_hash")
        if self.sequence > 1:
            if not self.previous_checkpoint_hash or not self.previous_checkpoint_hash.startswith("sha256:"):
                raise ValueError("sequence > 1 requires valid previous_checkpoint_hash")

        # Deduplicate list preserving order
        seen = set()
        clean_apps = []
        for item in self.pending_approval_ids:
            if item and item not in seen:
                seen.add(item)
                clean_apps.append(item)
        self.pending_approval_ids = clean_apps

        return self


class MissionCheckpointPage(BaseModel):
    mission_id: str
    checkpoints: list[MissionCheckpointRecord]
    count: int
    after_sequence: int
    next_after_sequence: int | None = None
    has_more: bool = False
    source: Literal["checkpoint_store", "empty"]
    integrity_verified: bool
    last_sequence: int
    last_checkpoint_hash: str | None = None


class MissionCheckpointIntegrity(BaseModel):
    mission_id: str
    valid: bool
    checkpoint_count: int
    last_sequence: int
    last_checkpoint_hash: str | None = None
    error_code: str | None = None
    error_sequence: int | None = None


class MissionControlResponse(BaseModel):
    mission_id: str
    command_status: str
    pause_requested: bool
    active_checkpoint_id: str | None = None
    control_version: int
    resume_count: int
    message: str


class MissionRecoveryStatusResponse(BaseModel):
    mission_id: str
    command_status: str
    recovery_status: MissionRecoveryStatus
    latest_failure: MissionFailureClassification | None = None
    recovery_attempts_for_failure: int = Field(ge=0)
    recovery_count: int = Field(ge=0)
    recovery_checkpoint_id: str | None = None
    recovery_task_id: str | None = None
    recovery_started_at: datetime | None = None
    recovery_completed_at: datetime | None = None
    control_version: int = Field(ge=0)
    can_recover: bool
    blocked_reason: str | None = None


class RecoverMissionRequest(BaseModel):
    failure_id: str | None = Field(default=None, max_length=160)
    expected_control_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def normalize_failure_id(self) -> "RecoverMissionRequest":
        self.failure_id = (self.failure_id or "").strip() or None
        return self


class RecoverMissionResponse(BaseModel):
    mission_id: str
    failure_id: str
    task_id: str
    accepted: bool
    scheduled: bool
    idempotent: bool
    command_status: str
    recovery_status: MissionRecoveryStatus
    recovery_attempts_for_failure: int = Field(ge=0)
    recovery_count: int = Field(ge=0)
    recovery_checkpoint_id: str | None = None
    control_version: int = Field(ge=0)
    message: str


class MissionHistoryCheckpointSummary(BaseModel):
    checkpoint_id: str = Field(min_length=1, max_length=160)
    sequence: int = Field(ge=1)
    created_at: datetime
    reason: str = Field(min_length=1, max_length=80)
    status_at_checkpoint: str = Field(min_length=1, max_length=80)
    resume_target_status: str | None = Field(default=None, max_length=80)
    current_task_id: str | None = Field(default=None, max_length=160)
    resumable: bool
    consumed_by_resume: bool
    checkpoint_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def normalize_fields(self) -> "MissionHistoryCheckpointSummary":
        self.checkpoint_id = self.checkpoint_id.strip()
        self.reason = self.reason.strip()
        self.status_at_checkpoint = self.status_at_checkpoint.strip()
        self.resume_target_status = (self.resume_target_status or "").strip() or None
        self.current_task_id = (self.current_task_id or "").strip() or None
        if not self.checkpoint_id or not self.reason or not self.status_at_checkpoint:
            raise ValueError("checkpoint summary fields must not be empty")
        return self


class MissionHistoryFailureSummary(BaseModel):
    failure_id: str = Field(min_length=1, max_length=160)
    failure_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_receipt_id: str | None = Field(default=None, max_length=160)
    phase: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    severity: str = Field(min_length=1, max_length=40)
    error_code: str = Field(min_length=1, max_length=160)
    retryable: bool
    recoverable: bool
    recommended_action: str = Field(min_length=1, max_length=80)
    task_attempt: int = Field(ge=0)
    mission_recovery_count: int = Field(ge=0)

    @model_validator(mode="after")
    def normalize_fields(self) -> "MissionHistoryFailureSummary":
        for name in ("failure_id", "phase", "category", "severity", "error_code", "recommended_action"):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            setattr(self, name, value)
        self.source_receipt_id = (self.source_receipt_id or "").strip() or None
        return self


class MissionHistoryRecoverySummary(BaseModel):
    status: Literal["started", "scheduled", "completed", "blocked", "failed"]
    failure_id: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=80)
    recovery_attempts_for_failure: int = Field(default=0, ge=0)
    recovery_count: int = Field(default=0, ge=0)
    recovery_checkpoint_id: str | None = Field(default=None, max_length=160)
    control_version: int | None = Field(default=None, ge=0)
    scheduled: bool | None = None


class MissionHistoryEntry(BaseModel):
    sequence: int = Field(ge=1)
    event_id: str = Field(min_length=1, max_length=160)
    occurred_at: datetime
    event_type: str = Field(min_length=1, max_length=160)
    canonical_kind: Literal["mission", "plan", "step", "tool", "approval", "checkpoint", "recovery", "system"]
    actor: str = Field(min_length=1, max_length=160)
    task_id: str | None = Field(default=None, max_length=160)
    approval_id: str | None = Field(default=None, max_length=160)
    label: str = Field(min_length=1, max_length=160)
    command_status: str | None = Field(default=None, max_length=80)
    task_status: str | None = Field(default=None, max_length=80)
    receipt: ExecutionReceiptSummary | None = None
    checkpoint: MissionHistoryCheckpointSummary | None = None
    failure: MissionHistoryFailureSummary | None = None
    recovery: MissionHistoryRecoverySummary | None = None
    event_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class MissionHistoryPage(BaseModel):
    mission_id: str
    command_status: str
    terminal: bool
    entries: list[MissionHistoryEntry]
    count: int = Field(ge=0)
    after_sequence: int = Field(ge=0)
    next_after_sequence: int | None = Field(default=None, ge=1)
    has_more: bool
    source: Literal["journal", "legacy_command_events", "empty"]
    integrity_verified: bool
    last_sequence: int = Field(ge=0)
    last_event_hash: str | None = None


class MissionTaskPostRunSummary(BaseModel):
    task_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=500)
    status: str = Field(min_length=1, max_length=80)
    attempts: int = Field(ge=0)
    verification_failures: int = Field(ge=0)
    continuation_resumes: int = Field(ge=0)
    recovery_reason: str | None = Field(default=None, max_length=300)
    materialized_file_count: int = Field(ge=0)
    approval_count: int = Field(ge=0)


class MissionPostRunSummary(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    mission_id: str
    command_status: Literal["completed", "failed"]
    outcome: Literal["succeeded", "failed"]
    terminal: Literal[True] = True
    goal: str = Field(max_length=2000)
    created_at: str
    updated_at: str
    duration_ms: int | None = Field(default=None, ge=0)
    task_count: int = Field(ge=0)
    completed_task_count: int = Field(ge=0)
    failed_task_count: int = Field(ge=0)
    waiting_task_count: int = Field(ge=0)
    other_task_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    receipt_count: int = Field(ge=0)
    checkpoint_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    recovery_count: int = Field(ge=0)
    resume_count: int = Field(ge=0)
    approval_count: int = Field(ge=0)
    execution_succeeded_count: int = Field(ge=0)
    execution_failed_count: int = Field(ge=0)
    execution_cancelled_count: int = Field(ge=0)
    execution_timed_out_count: int = Field(ge=0)
    total_execution_duration_ms: int = Field(ge=0)
    affected_file_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    unlinked_receipt_count: int = Field(ge=0)
    unlinked_checkpoint_count: int = Field(ge=0)
    latest_failure: MissionFailureClassification | None = None
    tasks: list[MissionTaskPostRunSummary]
    highlights: list[str] = Field(max_length=12)
    warnings: list[str] = Field(max_length=12)
    history_source: Literal["journal", "legacy_command_events", "empty"]
    integrity_verified: bool
    last_event_sequence: int = Field(ge=0)
    last_event_hash: str | None = None
    last_receipt_sequence: int = Field(ge=0)
    last_receipt_hash: str | None = None
    last_checkpoint_sequence: int = Field(ge=0)
    last_checkpoint_hash: str | None = None
    summary_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_summary_counts(self) -> "MissionPostRunSummary":
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("task IDs must be unique")
        if self.task_count != len(self.tasks):
            raise ValueError("task_count must equal tasks length")
        if self.completed_task_count + self.failed_task_count + self.waiting_task_count + self.other_task_count != self.task_count:
            raise ValueError("task status counts must equal task_count")
        if self.execution_succeeded_count + self.execution_failed_count + self.execution_cancelled_count + self.execution_timed_out_count != self.receipt_count:
            raise ValueError("execution outcome counts must equal receipt_count")
        if any(len(item) > 300 for item in self.highlights):
            raise ValueError("highlight exceeds 300 characters")
        if any(len(item) > 500 for item in self.warnings):
            raise ValueError("warning exceeds 500 characters")
        return self


class CreateMissionBranchRequest(BaseModel):
    checkpoint_id: str = Field(min_length=1, max_length=160)
    expected_checkpoint_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    label: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def normalize_branch_request(self) -> "CreateMissionBranchRequest":
        self.checkpoint_id = self.checkpoint_id.strip()
        self.idempotency_key = self.idempotency_key.strip()
        self.label = (self.label or "").strip()[:160] or None
        if self.label and (re.search(r"(?i)\b(?:token|password|api[_-]?key|authorization|cookie|credential|private[_-]?key|session[_-]?token)\b\s*[:=]", self.label) or re.search(r"(?i)(?:[a-z]:\\|/(?:home|users|root|tmp)/)", self.label) or "traceback (most recent call last)" in self.label.casefold()):
            raise ValueError("label contains unsafe diagnostic data")
        return self


class ActivateMissionBranchRequest(BaseModel):
    expected_control_version: int | None = Field(default=None, ge=0)
    expected_source_checkpoint_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    confirm_shared_workspace: bool

    @model_validator(mode="after")
    def require_workspace_confirmation(self) -> "ActivateMissionBranchRequest":
        if self.confirm_shared_workspace is not True:
            raise ValueError("confirm_shared_workspace must be true")
        return self


class MissionBranchResponse(BaseModel):
    parent_mission_id: str
    child_mission_id: str
    root_mission_id: str
    source_checkpoint_id: str
    source_checkpoint_sequence: int = Field(ge=1)
    source_checkpoint_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_checkpoint_state_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    branch_depth: int = Field(ge=1, le=64)
    branch_label: str | None = None
    branch_workspace_mode: MissionBranchWorkspaceMode
    child_status: str
    child_active_checkpoint_id: str
    child_control_version: int = Field(ge=0)
    created: bool
    execution_started: bool = False
    activation_required: bool = True


class MissionBranchSummary(BaseModel):
    mission_id: str
    status: str
    branch_depth: int = Field(ge=1, le=64)
    source_checkpoint_id: str
    source_checkpoint_sequence: int = Field(ge=1)
    source_checkpoint_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    branch_label: str | None = None
    created_at: str
    activation_required: bool
    activated_at: datetime | None = None


class MissionLineageResponse(BaseModel):
    mission_id: str
    root_mission_id: str
    parent_mission_id: str | None
    branch_depth: int = Field(ge=0, le=64)
    source_checkpoint_id: str | None = None
    source_checkpoint_sequence: int | None = Field(default=None, ge=1)
    source_checkpoint_hash: str | None = None
    source_checkpoint_state_hash: str | None = None
    ancestor_mission_ids: list[str] = Field(default_factory=list)
    direct_children: list[MissionBranchSummary] = Field(default_factory=list)
    direct_child_count: int = Field(ge=0)
    lineage_complete: bool

