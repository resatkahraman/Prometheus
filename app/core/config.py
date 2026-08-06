from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Prometheus"
    environment: str = "development"
    http_remote_access_enabled: bool = False
    http_auth_token: SecretStr | None = None

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    github_token: str | None = None
    github_model: str = "openai/gpt-4.1-mini"
    github_base_url: str = "https://models.github.ai"
    github_api_version: str = "2026-03-10"
    github_route_enabled: bool = True

    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_fast_model: str = "llama-3.1-8b-instant"
    groq_strong_model: str = "llama-3.3-70b-versatile"

    local_model_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_expert_model: str = "qwen3.5:9b"
    ollama_context_tokens: int = Field(default=4_096, ge=1_024, le=16_384)
    ollama_max_output_tokens: int = Field(default=2_048, ge=128, le=4_096)
    ollama_keep_alive: str = "5m"
    local_model_timeout_seconds: float = Field(
        default=45.0,
        ge=10.0,
        le=600.0,
    )
    local_expert_timeout_seconds: float = Field(
        default=180.0,
        ge=30.0,
        le=900.0,
    )
    local_model_max_input_chars: int = Field(
        default=10_000,
        ge=2_000,
        le=50_000,
    )
    local_model_max_source_chars: int = Field(
        default=9_000,
        ge=500,
        le=30_000,
    )
    local_model_max_attempts_per_task: int = Field(
        default=0,
        ge=0,
        le=100,
    )

    fallback_order: str = "groq_fast,gemini,github,groq_strong"

    request_timeout_seconds: float = Field(default=75.0, ge=5.0, le=300.0)
    # httpx read timeouts measure inactivity, not total request duration.
    # This wall-clock ceiling guarantees that a provider which keeps the
    # connection alive cannot consume an entire Supervisor task timeout.
    provider_call_wall_timeout_seconds: float = Field(
        default=90.0,
        ge=5.0,
        le=300.0,
    )
    max_retries: int = Field(default=2, ge=0, le=5)
    max_input_chars: int = Field(default=40_000, ge=1_000, le=500_000)
    max_output_tokens: int = Field(default=1_600, ge=64, le=16_384)
    groq_fast_max_output_tokens: int = Field(default=700, ge=128, le=2_048)
    max_parallel_providers: int = Field(default=3, ge=1, le=8)

    gemini_daily_request_budget: int = Field(default=450, ge=0, le=100_000)
    github_daily_request_budget: int = Field(default=120, ge=0, le=100_000)
    groq_fast_daily_request_budget: int = Field(default=500, ge=0, le=100_000)
    groq_strong_daily_request_budget: int = Field(default=150, ge=0, le=100_000)
    verify_daily_budget: int = Field(default=15, ge=0, le=10_000)

    # Free-only is the master lock. Paid routes stay unavailable even if a
    # future provider key is present until the user deliberately disables it.
    free_only_mode: bool = True
    paid_models_enabled: bool = False
    monthly_paid_budget_usd: float = Field(default=0.0, ge=0.0, le=10_000.0)
    mission_budget_enabled: bool = True
    mission_max_model_calls: int = Field(default=24, ge=1, le=1_000)
    mission_max_estimated_input_tokens: int = Field(
        default=60_000,
        ge=1_000,
        le=10_000_000,
    )
    free_quota_conserve_ratio: float = Field(
        default=0.10,
        ge=0.0,
        le=0.50,
    )
    free_quota_max_pressure_penalty: float = Field(
        default=35.0,
        ge=0.0,
        le=100.0,
    )
    free_provider_max_retries: int = Field(
        default=1,
        ge=0,
        le=3,
    )

    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=86_400, ge=60, le=2_592_000)
    operations_database_path: Path = Path("data/orchestra_ops.db")

    circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    circuit_cooldown_seconds: int = Field(default=300, ge=10, le=86_400)

    agent_max_steps: int = Field(default=12, ge=1, le=40)
    agent_max_model_calls: int = Field(default=16, ge=1, le=50)
    agent_step_output_tokens: int = Field(default=1_000, ge=128, le=4_096)
    agent_tool_result_max_chars: int = Field(default=12_000, ge=500, le=100_000)
    agent_session_ttl_seconds: int = Field(default=3_600, ge=300, le=86_400)
    agent_approval_replay_ttl_seconds: int = Field(
        default=3_600,
        ge=60,
        le=86_400,
    )
    agent_post_approval_extra_steps: int = Field(
        default=5,
        ge=0,
        le=20,
    )
    agent_post_approval_extra_model_calls: int = Field(
        default=6,
        ge=0,
        le=20,
    )
    agent_quality_max_retries: int = Field(default=2, ge=0, le=5)
    agent_auto_context_max_files: int = Field(default=4, ge=0, le=12)
    agent_auto_context_max_lines: int = Field(default=180, ge=20, le=500)
    project_memory_enabled: bool = True
    project_memory_database_path: Path = Path(".adam/project_memory.db")
    project_memory_attention_budget_chars: int = Field(
        default=800,
        ge=500,
        le=20_000,
    )
    project_memory_hypotheses_enabled: bool = True
    project_dna_enabled: bool = True
    project_dna_max_file_bytes: int = Field(
        default=32_768,
        ge=4_096,
        le=131_072,
    )
    project_dna_context_max_chars: int = Field(
        default=8_000,
        ge=1_000,
        le=32_000,
    )
    context_compiler_mode: Literal["off", "shadow", "active"] = "active"
    context_compiler_shadow_budget_chars: int = Field(
        default=8_000,
        ge=2_000,
        le=50_000,
    )
    context_rag_enabled: bool = True
    context_rag_max_cards: int = Field(default=32, ge=1, le=200)
    context_rag_scan_limit: int = Field(default=1_000, ge=50, le=20_000)
    experience_kernel_enabled: bool = True
    improvement_database_path: Path = Path(".adam/improvement.db")
    orientation_cache_budget_chars: int = Field(
        default=1_400,
        ge=300,
        le=8_000,
    )
    orientation_cache_scan_limit: int = Field(
        default=300,
        ge=20,
        le=5_000,
    )
    local_embedding_enabled: bool = True
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    embedding_timeout_seconds: float = Field(
        default=20.0,
        ge=2.0,
        le=120.0,
    )
    embedding_recall_batch_size: int = Field(default=8, ge=1, le=32)
    learned_router_mode: Literal["off", "shadow", "active"] = "shadow"
    forge_enabled: bool = True
    forge_source_mutation_enabled: bool = False
    agent_context_max_chars: int = Field(
        default=24_000,
        ge=4_000,
        le=100_000,
    )
    agent_context_base_max_chars: int = Field(
        default=14_000,
        ge=1_000,
        le=80_000,
    )
    agent_project_context_max_chars: int = Field(
        default=7_000,
        ge=500,
        le=50_000,
    )
    agent_context_memory_max_chars: int = Field(
        default=3_000,
        ge=500,
        le=20_000,
    )
    agent_context_recent_messages: int = Field(default=2, ge=0, le=12)
    agent_tool_content_max_chars: int = Field(
        default=6_000,
        ge=500,
        le=50_000,
    )
    agent_context_expansion_max_requests: int = Field(
        default=2,
        ge=0,
        le=6,
    )
    agent_context_expansion_max_files: int = Field(
        default=3,
        ge=1,
        le=12,
    )
    agent_context_expansion_max_lines: int = Field(
        default=220,
        ge=20,
        le=500,
    )
    agent_generated_evidence_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
    )
    planning_integrity_strict: bool = True
    planning_max_tasks: int = Field(default=24, ge=1, le=100)
    delivery_status_guard_enabled: bool = True
    execution_evidence_guard_enabled: bool = True
    protocol_repair_max_retries: int = Field(default=2, ge=0, le=5)
    supervisor_command_ttl_seconds: int = Field(
        default=2_592_000,
        ge=900,
        le=31_536_000,
    )
    supervisor_persistence_enabled: bool = True
    supervisor_database_path: Path = Path(".adam/supervisor.db")
    supervisor_default_autonomy_mode: Literal[
        "locked", "task", "trusted"
    ] = "task"
    supervisor_trusted_autonomy_enabled: bool = False
    supervisor_same_failure_limit: int = Field(default=2, ge=1, le=10)
    supervisor_max_task_attempts: int = Field(default=3, ge=1, le=10)
    supervisor_max_continuation_resumes: int = Field(
        default=20, ge=1, le=50
    )
    supervisor_task_agent_max_steps: int = Field(
        default=24,
        ge=4,
        le=40,
    )
    supervisor_task_agent_max_model_calls: int = Field(
        default=28,
        ge=4,
        le=50,
    )
    supervisor_fresh_recovery_timeout_seconds: float = Field(
        default=150.0,
        ge=10.0,
        le=600.0,
    )
    supervisor_focused_step_timeout_seconds: float = Field(
        default=180.0,
        ge=10.0,
        le=300.0,
    )
    supervisor_focused_provider_retry_limit: int = Field(
        default=1,
        ge=0,
        le=3,
    )
    supervisor_focused_step_max_steps: int = Field(
        default=5,
        ge=2,
        le=12,
    )
    supervisor_focused_step_max_model_calls: int = Field(
        default=5,
        ge=1,
        le=12,
    )
    supervisor_focused_file_output_tokens: int = Field(
        default=8_192,
        ge=1_024,
        le=16_384,
    )
    supervisor_focused_context_max_chars: int = Field(
        default=8_000,
        ge=2_000,
        le=50_000,
    )
    supervisor_focused_related_full_files: int = Field(
        default=1,
        ge=0,
        le=8,
    )
    supervisor_task_agent_timeout_seconds: float = Field(
        default=300.0,
        ge=10.0,
        le=1_800.0,
    )
    supervisor_reviewer_timeout_seconds: float = Field(
        default=180.0,
        ge=10.0,
        le=900.0,
    )
    supervisor_auto_run_max_tasks: int = Field(default=24, ge=1, le=100)
    supervisor_single_active_task: bool = True
    supervisor_auto_evidence_reconcile: bool = True
    supervisor_auto_review: bool = True
    supervisor_max_events: int = Field(default=300, ge=20, le=2_000)
    supervisor_approval_background: bool = True
    supervisor_recover_after_applied_tool: bool = True
    supervisor_planner_attempts: int = Field(default=3, ge=1, le=6)
    supervisor_planner_retry_routes: bool = True
    supervisor_planner_engine: str = "typed_kernel"
    supervisor_planner_read_max_lines: int = Field(
        default=120,
        ge=20,
        le=500,
    )
    supervisor_planner_attempt_timeout_seconds: float = Field(
        default=110.0,
        ge=0.05,
        le=600.0,
    )
    supervisor_planner_total_timeout_seconds: float = Field(
        default=300.0,
        ge=0.1,
        le=1_800.0,
    )
    supervisor_operation_heartbeat_seconds: float = Field(
        default=4.0,
        ge=0.05,
        le=60.0,
    )
    supervisor_stale_operation_seconds: float = Field(
        default=150.0,
        ge=1.0,
        le=3_600.0,
    )
    supervisor_approval_tool_timeout_seconds: float = Field(
        default=210.0,
        ge=5.0,
        le=3_600.0,
    )
    supervisor_agent_continuation_timeout_seconds: float = Field(
        default=90.0,
        ge=5.0,
        le=600.0,
    )
    supervisor_cancellation_grace_seconds: float = Field(
        default=1.0,
        ge=0.05,
        le=15.0,
    )

    workspace_root: Path = Field(
        default=Path("workspace"),
        validation_alias=AliasChoices(
            "workspace_root",
            "PROMETHEUS_WORKSPACE_ROOT",
            "ADAM_WORKSPACE_ROOT",
            "WORKSPACE_ROOT",
        ),
    )
    workspace_max_file_bytes: int = Field(
        default=1_000_000,
        ge=1_000,
        le=20_000_000,
    )
    workspace_max_search_results: int = Field(
        default=100,
        ge=1,
        le=1_000,
    )
    command_timeout_seconds: int = Field(default=300, ge=5, le=3_600)
    command_output_max_chars: int = Field(
        default=30_000,
        ge=1_000,
        le=500_000,
    )
    approval_ttl_seconds: int = Field(default=1_800, ge=60, le=86_400)

    usage_log_path: Path = Path("data/usage.jsonl")
    arena_history_directory: Path = Path("data")
    arena_history_max_databases: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        token = (
            self.http_auth_token.get_secret_value().strip()
            if self.http_auth_token is not None
            else ""
        )
        if self.http_remote_access_enabled and len(token) < 32:
            raise ValueError(
                "HTTP_REMOTE_ACCESS_ENABLED=true için HTTP_AUTH_TOKEN "
                "en az 32 karakter olmalı."
            )
        if (
            self.supervisor_default_autonomy_mode == "trusted"
            and not self.supervisor_trusted_autonomy_enabled
        ):
            raise ValueError(
                "SUPERVISOR_DEFAULT_AUTONOMY_MODE=trusted için "
                "SUPERVISOR_TRUSTED_AUTONOMY_ENABLED=true olmalı."
            )
        return self

    @property
    def fallback_routes(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.fallback_order.split(",")
            if item.strip()
        ]

    @property
    def effective_paid_models_enabled(self) -> bool:
        return (
            not self.free_only_mode
            and self.paid_models_enabled
            and self.monthly_paid_budget_usd > 0
        )

    def daily_budget_for_route(self, route_key: str) -> int:
        budgets = {
            "local_qwen": 0,
            "local_expert": 0,
            "gemini": self.gemini_daily_request_budget,
            "github": self.github_daily_request_budget,
            "groq_fast": self.groq_fast_daily_request_budget,
            "groq_strong": self.groq_strong_daily_request_budget,
        }
        return budgets.get(route_key.strip().lower(), 0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
