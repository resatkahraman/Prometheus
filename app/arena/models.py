from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArenaVerification:
    name: str
    preset: str
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArenaScenario:
    id: str
    title: str
    goal: str
    seed_files: dict[str, str]
    required_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    verifications: tuple[ArenaVerification, ...]
    max_model_calls: int
    max_estimated_input_tokens: int
    target_model_calls: int
    target_total_tokens: int
    minimum_calls_to_start: int = 3
    timeout_seconds: int = 600
    initial_verification_should_fail: bool = True
    required_agents: tuple[str, ...] = ()
    minimum_handoffs: int = 0


@dataclass(frozen=True)
class ArenaQuotaRoute:
    key: str
    provider: str
    used: int
    budget: int
    remaining: int | None
    reserved: int
    usable_remaining: int | None


@dataclass(frozen=True)
class ArenaQuotaPlan:
    allowed: bool
    reason: str
    minimum_calls: int
    usable_calls: int | None
    routes: tuple[ArenaQuotaRoute, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArenaVerificationResult:
    name: str
    preset: str
    success: bool
    exit_code: int | None
    output: str


@dataclass(frozen=True)
class ArenaScore:
    total: float
    completion: float
    verification: float
    artifacts: float
    autonomy: float
    efficiency: float
    reliability: float


@dataclass
class ArenaResult:
    run_id: str
    scenario_id: str
    scenario_title: str
    mission_id: str | None
    status: str
    failure_reason: str | None
    elapsed_seconds: float
    workspace: str
    approvals_applied: int
    decisions_answered: int
    required_paths_ok: bool
    missing_required_paths: list[str]
    protected_paths_ok: bool
    changed_protected_paths: list[str]
    baseline_verifications: list[ArenaVerificationResult]
    verifications: list[ArenaVerificationResult]
    usage: dict[str, Any]
    mission_usage: dict[str, Any] | None
    task_attempts: int
    failure_records: int
    score: ArenaScore
    coordination: dict[str, Any] = field(default_factory=dict)
    context_compiler: dict[str, Any] = field(default_factory=dict)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    event_counts: dict[str, int] = field(default_factory=dict)
    notable_events: list[dict[str, Any]] = field(default_factory=list)
    last_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
