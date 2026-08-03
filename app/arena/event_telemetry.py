from typing import Any, Mapping

_NOTABLE_EVENT_TYPES = frozenset(
    (
        "deterministic_contract_repair_selected",
        "focused_provider_retry_scheduled",
        "focused_provider_retry_exhausted",
        "task_watchdog_recovered",
        "existing_target_verification_first",
        "task_assignment",
        "review_accept",
        "completion",
    )
)


def summarize_arena_events(
    events: Any,
    notable_limit: int = 100,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts: dict[str, int] = {}
    notable: list[dict[str, Any]] = []

    for raw in events or []:
        if isinstance(raw, Mapping):
            data = dict(raw)
        elif hasattr(raw, "model_dump"):
            data = raw.model_dump()
        elif hasattr(raw, "__dict__"):
            data = dict(raw.__dict__)
        else:
            continue

        event_type = data.get("type")
        if not event_type or not isinstance(event_type, str):
            continue

        counts[event_type] = counts.get(event_type, 0) + 1
        if event_type in _NOTABLE_EVENT_TYPES:
            notable.append(data)

    if notable_limit > 0 and len(notable) > notable_limit:
        notable = notable[-notable_limit:]

    return counts, notable
