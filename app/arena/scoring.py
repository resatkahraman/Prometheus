from __future__ import annotations

from app.arena.models import ArenaScenario, ArenaScore


def score_arena_run(
    *,
    scenario: ArenaScenario,
    status: str,
    verification_passed: int,
    verification_total: int,
    required_paths_ok: bool,
    protected_paths_ok: bool,
    approvals: int,
    decisions: int,
    model_calls: int,
    total_tokens: int,
    failed_calls: int,
    task_attempts: int,
    task_count: int,
    failure_records: int,
    work_sharing_ok: bool = True,
) -> ArenaScore:
    completion = 40.0 if status == "completed" else 0.0
    verification = (
        25.0 * verification_passed / verification_total
        if verification_total
        else 0.0
    )
    artifacts = (
        (5.0 if required_paths_ok else 0.0)
        + (5.0 if protected_paths_ok else 0.0)
    )
    autonomy = max(0.0, 10.0 - approvals * 2.0 - decisions * 1.5)

    call_ratio = model_calls / max(1, scenario.target_model_calls)
    token_ratio = total_tokens / max(1, scenario.target_total_tokens)
    pressure = max(call_ratio, token_ratio)
    efficiency = 10.0 if pressure <= 1.0 else max(0.0, 20.0 - 10.0 * pressure)

    retries = max(0, task_attempts - task_count)
    reliability_penalty = (
        failed_calls * 2.0
        + retries * 0.75
        + failure_records * 0.5
    )
    reliability = max(0.0, 5.0 - reliability_penalty)

    total = (
        completion
        + verification
        + artifacts
        + autonomy
        + efficiency
        + reliability
    )
    if status != "completed":
        total = min(total, 60.0)
    elif scenario.required_agents and not work_sharing_ok:
        total = min(total, 70.0)
    return ArenaScore(
        total=round(total, 2),
        completion=round(completion, 2),
        verification=round(verification, 2),
        artifacts=round(artifacts, 2),
        autonomy=round(autonomy, 2),
        efficiency=round(efficiency, 2),
        reliability=round(reliability, 2),
    )
