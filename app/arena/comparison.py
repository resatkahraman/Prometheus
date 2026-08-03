from __future__ import annotations

from collections import Counter
from typing import Any, Callable


MetricGetter = Callable[[dict[str, Any]], float]


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _integer(value: object, default: int = 0) -> int:
    return int(_number(value, float(default)))


def _score(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("score")
    if isinstance(raw, dict):
        return raw
    return {"total": _number(raw)}


def _usage(payload: dict[str, Any]) -> dict[str, Any]:
    return _mapping(payload.get("usage"))


def _coordination(payload: dict[str, Any]) -> dict[str, Any]:
    return _mapping(payload.get("coordination"))


def _verification_map(payload: dict[str, Any]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for index, item in enumerate(_items(payload.get("verifications"))):
        name = str(
            item.get("name")
            or item.get("preset")
            or f"verification-{index + 1}"
        )
        if name in results:
            name = f"{name}#{index + 1}"
        results[name] = bool(item.get("success"))
    return results


def _task_status_counts(payload: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for task in _items(payload.get("tasks")):
        counts[str(task.get("status") or "unknown")] += 1
    return counts


def _completed_agents(payload: dict[str, Any]) -> set[str]:
    coordination = _coordination(payload)
    raw = coordination.get("completed_agents")
    if isinstance(raw, list):
        return {str(item) for item in raw if str(item).strip()}
    return {
        str(task.get("assigned_agent"))
        for task in _items(payload.get("tasks"))
        if task.get("status") == "completed" and task.get("assigned_agent")
    }


def _handoff_count(payload: dict[str, Any]) -> int:
    coordination = _coordination(payload)
    configured = coordination.get("handoff_count")
    if configured is not None:
        return _integer(configured)
    return len(_items(payload.get("handoffs")))


def _metric(
    *,
    key: str,
    label: str,
    base: dict[str, Any],
    candidate: dict[str, Any],
    getter: MetricGetter,
    higher_is_better: bool,
) -> dict[str, Any]:
    base_value = getter(base)
    candidate_value = getter(candidate)
    delta = candidate_value - base_value
    if abs(delta) < 1e-9:
        outcome = "unchanged"
    elif (delta > 0) == higher_is_better:
        outcome = "improved"
    else:
        outcome = "regressed"
    return {
        "key": key,
        "label": label,
        "base": base_value,
        "candidate": candidate_value,
        "delta": delta,
        "higher_is_better": higher_is_better,
        "outcome": outcome,
    }


def _classify(outcomes: list[str]) -> str:
    improved = any(item == "improved" for item in outcomes)
    regressed = any(item == "regressed" for item in outcomes)
    if improved and regressed:
        return "mixed"
    if improved:
        return "improved"
    if regressed:
        return "regressed"
    return "unchanged"


def _run_summary(payload: dict[str, Any]) -> dict[str, Any]:
    verifications = _verification_map(payload)
    tasks = _task_status_counts(payload)
    return {
        "run_id": payload.get("run_id"),
        "scenario_id": payload.get("scenario_id"),
        "scenario_title": payload.get(
            "scenario_title",
            payload.get("scenario_id"),
        ),
        "status": payload.get("status"),
        "score": _number(_score(payload).get("total")),
        "elapsed_seconds": _number(payload.get("elapsed_seconds")),
        "model_calls": _integer(_usage(payload).get("model_calls")),
        "total_tokens": _integer(_usage(payload).get("total_tokens")),
        "task_attempts": _integer(payload.get("task_attempts")),
        "failure_records": _integer(payload.get("failure_records")),
        "successful_verifications": sum(verifications.values()),
        "failed_verifications": sum(not value for value in verifications.values()),
        "completed_tasks": tasks.get("completed", 0),
        "handoff_count": _handoff_count(payload),
        "completed_agents": sorted(_completed_agents(payload)),
        "failure_reason": payload.get("failure_reason"),
        "database": payload.get("database"),
    }


def compare_arena_runs(
    base: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic, read-only comparison of two Arena results."""

    base_summary = _run_summary(base)
    candidate_summary = _run_summary(candidate)
    same_scenario = (
        base_summary["scenario_id"] == candidate_summary["scenario_id"]
    )

    metrics = [
        _metric(
            key="score",
            label="Arena skoru",
            base=base,
            candidate=candidate,
            getter=lambda item: _number(_score(item).get("total")),
            higher_is_better=True,
        ),
        _metric(
            key="elapsed_seconds",
            label="Süre (sn)",
            base=base,
            candidate=candidate,
            getter=lambda item: _number(item.get("elapsed_seconds")),
            higher_is_better=False,
        ),
        _metric(
            key="model_calls",
            label="Model çağrısı",
            base=base,
            candidate=candidate,
            getter=lambda item: _number(_usage(item).get("model_calls")),
            higher_is_better=False,
        ),
        _metric(
            key="total_tokens",
            label="Toplam token",
            base=base,
            candidate=candidate,
            getter=lambda item: _number(_usage(item).get("total_tokens")),
            higher_is_better=False,
        ),
        _metric(
            key="task_attempts",
            label="Görev denemesi",
            base=base,
            candidate=candidate,
            getter=lambda item: _number(item.get("task_attempts")),
            higher_is_better=False,
        ),
        _metric(
            key="failure_records",
            label="Hata kaydı",
            base=base,
            candidate=candidate,
            getter=lambda item: _number(item.get("failure_records")),
            higher_is_better=False,
        ),
    ]

    component_keys = (
        "completion",
        "verification",
        "artifacts",
        "autonomy",
        "efficiency",
        "reliability",
    )
    score_components = [
        _metric(
            key=key,
            label=key,
            base=base,
            candidate=candidate,
            getter=lambda item, component=key: _number(
                _score(item).get(component)
            ),
            higher_is_better=True,
        )
        for key in component_keys
    ]

    base_verifications = _verification_map(base)
    candidate_verifications = _verification_map(candidate)
    all_verification_names = sorted(
        set(base_verifications) | set(candidate_verifications)
    )
    newly_passing = [
        name
        for name in all_verification_names
        if not base_verifications.get(name, False)
        and candidate_verifications.get(name, False)
    ]
    newly_failing = [
        name
        for name in all_verification_names
        if base_verifications.get(name, False)
        and not candidate_verifications.get(name, False)
    ]

    base_tasks = _task_status_counts(base)
    candidate_tasks = _task_status_counts(candidate)
    base_agents = _completed_agents(base)
    candidate_agents = _completed_agents(candidate)

    base_failure = str(base.get("failure_reason") or "").strip() or None
    candidate_failure = (
        str(candidate.get("failure_reason") or "").strip() or None
    )

    quality_outcomes: list[str] = []
    base_completed = base.get("status") == "completed"
    candidate_completed = candidate.get("status") == "completed"
    if base_completed != candidate_completed:
        quality_outcomes.append(
            "improved" if candidate_completed else "regressed"
        )
    quality_outcomes.append(metrics[0]["outcome"])
    if newly_passing:
        quality_outcomes.append("improved")
    if newly_failing:
        quality_outcomes.append("regressed")
    if base_failure and not candidate_failure:
        quality_outcomes.append("improved")
    if not base_failure and candidate_failure:
        quality_outcomes.append("regressed")
    for field in ("required_paths_ok", "protected_paths_ok"):
        base_value = bool(base.get(field))
        candidate_value = bool(candidate.get(field))
        if base_value != candidate_value:
            quality_outcomes.append(
                "improved" if candidate_value else "regressed"
            )

    efficiency_outcome = _classify(
        [item["outcome"] for item in metrics[1:]]
    )
    quality_outcome = _classify(quality_outcomes)
    if not same_scenario:
        verdict = "not_comparable"
    elif quality_outcome != "unchanged":
        verdict = quality_outcome
    else:
        verdict = efficiency_outcome

    highlights: list[str] = []
    if base.get("status") != candidate.get("status"):
        highlights.append(
            f"Durum {base.get('status')} → {candidate.get('status')}."
        )
    score_delta = metrics[0]["delta"]
    if abs(score_delta) >= 1e-9:
        highlights.append(f"Arena skoru {score_delta:+.1f} değişti.")
    if newly_passing:
        highlights.append(
            f"{len(newly_passing)} doğrulama yeni koşuda geçiyor."
        )
    if newly_failing:
        highlights.append(
            f"{len(newly_failing)} doğrulama yeni koşuda bozuldu."
        )
    if base_failure and not candidate_failure:
        highlights.append("Önceki failure_reason yeni koşuda çözüldü.")
    elif not base_failure and candidate_failure:
        highlights.append("Yeni koşu bir failure_reason üretti.")
    if not same_scenario:
        highlights.append(
            "Koşular farklı senaryolara ait; kalite kararı karşılaştırılamaz."
        )

    return {
        "same_scenario": same_scenario,
        "verdict": verdict,
        "quality_outcome": quality_outcome,
        "efficiency_outcome": efficiency_outcome,
        "base": base_summary,
        "candidate": candidate_summary,
        "metrics": metrics,
        "score_components": score_components,
        "verifications": {
            "base": base_verifications,
            "candidate": candidate_verifications,
            "newly_passing": newly_passing,
            "newly_failing": newly_failing,
        },
        "tasks": {
            "base_status_counts": dict(base_tasks),
            "candidate_status_counts": dict(candidate_tasks),
            "completed_delta": (
                candidate_tasks.get("completed", 0)
                - base_tasks.get("completed", 0)
            ),
        },
        "coordination": {
            "base_handoff_count": _handoff_count(base),
            "candidate_handoff_count": _handoff_count(candidate),
            "handoff_delta": _handoff_count(candidate) - _handoff_count(base),
            "agents_added": sorted(candidate_agents - base_agents),
            "agents_removed": sorted(base_agents - candidate_agents),
        },
        "failure": {
            "base_reason": base_failure,
            "candidate_reason": candidate_failure,
            "resolved": bool(base_failure and not candidate_failure),
            "introduced": bool(not base_failure and candidate_failure),
        },
        "highlights": highlights,
    }
