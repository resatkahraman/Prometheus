from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def summarize_usage(
    *,
    usage_log: Path,
    mission_id: str,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    if usage_log.exists():
        for line in usage_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("usage_scope") == mission_id:
                events.append(item)

    by_provider: dict[str, dict[str, int]] = {}
    for item in events:
        provider = str(item.get("provider") or "unknown")
        aggregate = by_provider.setdefault(
            provider,
            {
                "calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
            },
        )
        success = bool(item.get("success"))
        aggregate["calls"] += 1
        aggregate["successful_calls"] += int(success)
        aggregate["failed_calls"] += int(not success)
        aggregate["input_tokens"] += int(item.get("input_tokens") or 0)
        aggregate["output_tokens"] += int(item.get("output_tokens") or 0)
        aggregate["latency_ms"] += int(item.get("latency_ms") or 0)

    local_events = [item for item in events if bool(item.get("local"))]
    remote_events = [item for item in events if not bool(item.get("local"))]
    local_input_tokens = sum(
        int(item.get("input_tokens") or 0) for item in local_events
    )
    local_output_tokens = sum(
        int(item.get("output_tokens") or 0) for item in local_events
    )
    remote_input_tokens = sum(
        int(item.get("input_tokens") or 0) for item in remote_events
    )
    remote_output_tokens = sum(
        int(item.get("output_tokens") or 0) for item in remote_events
    )

    return {
        "events": len(events),
        "successful_calls": sum(
            item["successful_calls"] for item in by_provider.values()
        ),
        "failed_calls": sum(
            item["failed_calls"] for item in by_provider.values()
        ),
        "input_tokens": sum(item["input_tokens"] for item in by_provider.values()),
        "output_tokens": sum(item["output_tokens"] for item in by_provider.values()),
        "total_tokens": sum(
            item["input_tokens"] + item["output_tokens"]
            for item in by_provider.values()
        ),
        "local_calls": len(local_events),
        "local_tokens": local_input_tokens + local_output_tokens,
        "remote_calls": len(remote_events),
        "remote_tokens": remote_input_tokens + remote_output_tokens,
        "by_provider": by_provider,
    }
