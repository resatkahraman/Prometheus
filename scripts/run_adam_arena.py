from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.arena.catalog import get_scenario, list_scenarios
from app.arena.runner import ArenaRunner


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _progress(event: str, data: dict[str, Any]) -> None:
    print(
        "ARENA "
        + json.dumps(
            {"event": event, **data},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def _print_scenarios() -> None:
    for scenario in list_scenarios():
        print(
            f"{scenario.id:16} {scenario.title} "
            f"(tavan {scenario.max_model_calls} çağrı / "
            f"{scenario.max_estimated_input_tokens} giriş token)"
        )


async def _run(args: argparse.Namespace) -> int:
    runner = ArenaRunner(
        project_root=args.project,
        workspace_root=args.workspace_root,
        history_path=args.history,
        progress=_progress if not args.quiet else None,
        local_only=args.local_only,
    )
    scenario_ids = args.scenario or ["js_bugfix"]
    scenarios = [get_scenario(item) for item in scenario_ids]

    if args.show_history:
        rows = []
        selected = set(scenario_ids) if args.scenario else None
        for row in runner.history.history(limit=args.history_limit):
            if selected and row["scenario_id"] not in selected:
                continue
            payload = json.loads(row["result_json"])
            usage = payload.get("usage") or {}
            rows.append(
                {
                    "run_id": row["run_id"],
                    "scenario": row["scenario_id"],
                    "status": row["status"],
                    "score": row["score"],
                    "elapsed_seconds": row["elapsed_seconds"],
                    "model_calls": row["model_calls"],
                    "total_tokens": row["total_tokens"],
                    "verification_passed": all(
                        item.get("success") is True
                        for item in payload.get("verifications", [])
                    ),
                    "protected_paths_ok": payload.get(
                        "protected_paths_ok"
                    ),
                    "work_sharing_ok": (
                        payload.get("coordination") or {}
                    ).get("work_sharing_ok"),
                    "context_compiler": payload.get(
                        "context_compiler",
                        {},
                    ),
                    "usage_by_provider": usage.get("by_provider", {}),
                }
            )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if not args.live:
        plans = []
        for scenario in scenarios:
            quota = await runner.quota_plan(scenario)
            plans.append(
                {
                    "scenario": scenario.id,
                    "title": scenario.title,
                    "live": False,
                    "quota": quota.to_dict(),
                    "message": (
                        "Bu yalnızca plan ve kota kontrolüdür; model çağrısı "
                        "yapılmadı. Çalıştırmak için --live kullan."
                    ),
                }
            )
        print(json.dumps(plans, ensure_ascii=False, indent=2))
        return 0 if all(item["quota"]["allowed"] for item in plans) else 2

    results = []
    exit_code = 0
    for scenario in scenarios:
        try:
            result = await runner.run(scenario)
        except RuntimeError as exc:
            print(
                "ARENA_ERROR "
                + json.dumps(
                    {"scenario": scenario.id, "error": str(exc)},
                    ensure_ascii=False,
                )
            )
            return 2
        payload = result.to_dict()
        results.append(payload)
        verification_ok = all(
            item["success"] for item in payload["verifications"]
        )
        if (
            result.status != "completed"
            or not verification_ok
            or not result.required_paths_ok
            or not result.protected_paths_ok
            or not bool(
                (payload.get("coordination") or {}).get(
                    "work_sharing_ok",
                    True,
                )
            )
        ):
            exit_code = 1
    print("ARENA_RESULTS " + json.dumps(results, ensure_ascii=False))
    return exit_code


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prometheus'un yeteneklerini sabit, bağımsız doğrulamalı ve "
            "kota-korumalı senaryolarla ölçer."
        )
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=PROJECT_ROOT,
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=PROJECT_ROOT / "workspace" / "arena",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=PROJECT_ROOT / "data" / "arena.db",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        help="Birden fazla kez verilebilir. Varsayılan: js_bugfix",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Gerçek ücretsiz model çağrılarına açıkça izin verir.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help=(
            "Bu Arena sürecinde uzak sağlayıcıları kapatır; yalnızca yerel "
            "Ollama rotasının görevi tamamlayabildiğini kanıtlar."
        ),
    )
    parser.add_argument(
        "--show-history",
        action="store_true",
        help="Model çağrısı yapmadan kayıtlı Arena sonuçlarını gösterir.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=20,
        choices=range(1, 101),
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.list:
        _print_scenarios()
        raise SystemExit(0)
    args.project = args.project.resolve()
    args.workspace_root = args.workspace_root.resolve()
    args.history = args.history.resolve()
    return args


if __name__ == "__main__":
    _configure_console()
    raise SystemExit(asyncio.run(_run(_parse_args())))
