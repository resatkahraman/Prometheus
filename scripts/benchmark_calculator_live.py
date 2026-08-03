from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.orchestration.orchestrator import Orchestrator
from app.providers.registry import ProviderRegistry
from app.storage.operations import OperationsStore
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


DEFAULT_GOAL = "Basit bir web hesap makinesi yap."


def _usage_summary(
    *,
    usage_log: Path,
    mission_id: str,
) -> dict[str, object]:
    events: list[dict[str, object]] = []
    if usage_log.exists():
        for line in usage_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
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
                "failed_estimated_input_tokens": 0,
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
        if not success:
            aggregate["failed_estimated_input_tokens"] += int(
                item.get("estimated_input_tokens") or 0
            )

    return {
        "events": len(events),
        "successful_calls": sum(
            item["successful_calls"] for item in by_provider.values()
        ),
        "failed_calls": sum(
            item["failed_calls"] for item in by_provider.values()
        ),
        "input_tokens": sum(
            item["input_tokens"] for item in by_provider.values()
        ),
        "output_tokens": sum(
            item["output_tokens"] for item in by_provider.values()
        ),
        "total_tokens": sum(
            item["input_tokens"] + item["output_tokens"]
            for item in by_provider.values()
        ),
        "by_provider": by_provider,
    }


async def _run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    workspace = args.workspace.resolve()
    if workspace.exists():
        raise RuntimeError(
            f"Fresh benchmark workspace already exists: {workspace}"
        )
    workspace.mkdir(parents=True)

    artifacts = workspace / ".adam"
    usage_log = artifacts / "usage.jsonl"
    result_path = artifacts / "benchmark-result.json"
    settings = Settings(
        _env_file=project / ".env",
        workspace_root=workspace,
        operations_database_path=artifacts / "operations.db",
        usage_log_path=usage_log,
        supervisor_database_path=Path(".adam/supervisor.db"),
        project_memory_database_path=Path(".adam/project_memory.db"),
        cache_enabled=False,
        paid_models_enabled=False,
        monthly_paid_budget_usd=0.0,
        supervisor_approval_background=True,
    )

    store = OperationsStore(settings.operations_database_path)
    await store.initialize()
    providers = ProviderRegistry(settings)
    orchestrator = Orchestrator(
        settings=settings,
        registry=providers,
        store=store,
    )
    approvals = ApprovalManager(
        ttl_seconds=settings.approval_ttl_seconds
    )
    tools = build_default_tool_registry(
        settings=settings,
        approvals=approvals,
    )
    agents = build_default_agent_registry(tools.names())
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=tools,
        agents=agents,
    )
    supervisor = SupervisorService(
        settings=settings,
        agent=engine,
        agents=agents,
        tools=tools,
    )

    started = time.perf_counter()
    command = None
    last_snapshot = None
    approval_count = 0
    decision_count = 0
    try:
        print(f"BENCHMARK_START workspace={workspace}", flush=True)
        print(f"PROVIDERS {','.join(providers.names())}", flush=True)
        command = await supervisor.create(
            goal=args.goal,
            routing_mode="auto",
            auto_start=True,
            background=True,
            autonomy_mode="trusted",
        )
        print(f"MISSION_ID {command.id}", flush=True)

        deadline = time.monotonic() + args.timeout_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(1.0)
            command = await supervisor.get(command.id)
            task_counts: defaultdict[str, int] = defaultdict(int)
            for task in command.tasks:
                task_counts[task.status] += 1
            snapshot = (
                command.status,
                tuple(sorted(task_counts.items())),
                command.operation_phase,
                command.operation_message,
            )
            if snapshot != last_snapshot:
                print(
                    "STATE "
                    + json.dumps(
                        {
                            "status": command.status,
                            "tasks": dict(task_counts),
                            "phase": command.operation_phase,
                            "message": command.operation_message,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                last_snapshot = snapshot

            if command.status == "waiting_decision":
                pending = [
                    decision
                    for decision in command.decisions
                    if decision.status == "pending"
                ]
                if not pending:
                    raise RuntimeError(
                        "waiting_decision without a pending decision"
                    )
                decision = pending[0]
                print(
                    f"AUTO_DECISION {decision.id}: {decision.question}",
                    flush=True,
                )
                await supervisor.answer_decision(
                    command_id=command.id,
                    decision_id=decision.id,
                    answer=(
                        "En profesyonel, güvenilir ve basit ücretsiz çözümü "
                        "seç; gereksiz bağımlılık kullanma."
                    ),
                    replan_when_complete=True,
                    background=True,
                )
                decision_count += 1
                continue

            if command.status == "awaiting_approval":
                pending_tasks = [
                    task
                    for task in command.tasks
                    if task.status == "awaiting_approval"
                    and task.approval_state == "pending"
                ]
                if not pending_tasks:
                    continue
                task = pending_tasks[0]
                print(
                    f"AUTO_APPROVAL task={task.id} "
                    f"tool={task.approval_tool} "
                    f"version={task.approval_version}",
                    flush=True,
                )
                await supervisor.approve(
                    command_id=command.id,
                    task_id=task.id,
                    expected_approval_id=task.approval_id,
                    expected_approval_version=task.approval_version,
                    background=True,
                )
                approval_count += 1
                continue

            if command.status == "ready":
                print("AUTO_ADVANCE ready mission", flush=True)
                await supervisor.advance(
                    command_id=command.id,
                    max_tasks=settings.supervisor_auto_run_max_tasks,
                    background=True,
                )
                continue

            if command.status in {"completed", "failed"}:
                break
        else:
            raise TimeoutError(
                f"Benchmark exceeded {args.timeout_seconds} seconds"
            )

        elapsed = round(time.perf_counter() - started, 3)
        result = {
            "goal": args.goal,
            "mission_id": command.id,
            "status": command.status,
            "failure_reason": command.failure_reason,
            "elapsed_seconds": elapsed,
            "workspace": str(workspace),
            "approvals_applied": approval_count,
            "decisions_answered": decision_count,
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "agent": task.assigned_agent,
                    "status": task.status,
                    "attempts": task.attempts,
                    "verification": (
                        task.effective_verification or task.verification
                    ),
                    "files": task.materialized_files,
                    "failure_history": [
                        failure.model_dump()
                        for failure in task.failure_history
                    ],
                }
                for task in command.tasks
            ],
            "usage": _usage_summary(
                usage_log=usage_log,
                mission_id=command.id,
            ),
            "last_events": [
                event.model_dump() for event in command.events[-30:]
            ],
        }
        artifacts.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            "BENCHMARK_RESULT "
            + json.dumps(result, ensure_ascii=False),
            flush=True,
        )
        return 0 if command.status == "completed" else 1
    finally:
        await providers.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
    )
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_parse_args())))
