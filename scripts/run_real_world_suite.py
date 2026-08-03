from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.arena.catalog import get_scenario, list_scenarios
from app.arena.runner import ArenaRunner
from app.arena.suite import build_suite_report, render_suite_markdown


QUICK_SCENARIOS = (
    "calculator_from_scratch",
    "existing_vanilla_repair",
    "fastapi_task_api",
)
EXTENDED_SCENARIOS = tuple(item.id for item in list_scenarios())


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _progress(event: str, data: dict[str, Any]) -> None:
    print(
        "REAL_WORLD "
        + json.dumps(
            {"event": event, **data},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def _failure_payload(
    scenario_id: str,
    title: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "scenario_title": title,
        "status": "failed",
        "failure_reason": reason,
        "elapsed_seconds": 0,
        "required_paths_ok": False,
        "protected_paths_ok": False,
        "verifications": [],
        "coordination": {"work_sharing_ok": False},
        "usage": {},
        "score": {"total": 0},
        "workspace": None,
    }


async def _run(args: argparse.Namespace) -> int:
    scenario_ids = (
        tuple(args.scenario)
        if args.scenario
        else (EXTENDED_SCENARIOS if args.extended else QUICK_SCENARIOS)
    )
    scenarios = [get_scenario(item) for item in scenario_ids]
    local_only = not args.allow_remote
    runner = ArenaRunner(
        project_root=args.project,
        workspace_root=args.workspace_root,
        history_path=args.history,
        progress=None if args.quiet else _progress,
        local_only=local_only,
    )
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []

    for scenario in scenarios:
        print(f"\n=== {scenario.id}: {scenario.title} ===", flush=True)
        quota = await runner.quota_plan(scenario)
        if not quota.allowed:
            results.append(
                _failure_payload(
                    scenario.id,
                    scenario.title,
                    f"Kota kapısı: {quota.reason}",
                )
            )
            continue
        try:
            result = await runner.run(scenario)
            results.append(result.to_dict())
        except Exception as exc:
            results.append(
                _failure_payload(
                    scenario.id,
                    scenario.title,
                    f"{type(exc).__name__}: {exc}",
                )
            )

    report = build_suite_report(
        results,
        started_at=started_at,
        local_only=local_only,
    )
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = args.report_dir / f"real-world-{stamp}.json"
    markdown_path = args.report_dir / f"real-world-{stamp}.md"
    rendered_json = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    rendered_markdown = render_suite_markdown(report)
    json_path.write_text(rendered_json, encoding="utf-8")
    markdown_path.write_text(rendered_markdown, encoding="utf-8")
    (args.report_dir / "latest.json").write_text(
        rendered_json,
        encoding="utf-8",
    )
    (args.report_dir / "latest.md").write_text(
        rendered_markdown,
        encoding="utf-8",
    )

    print(
        "\nREAL_WORLD_REPORT "
        + json.dumps(
            {
                "success": report["success"],
                "passed": report["passed"],
                "total": report["total"],
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if report["success"] else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prometheus'u izole gerçek kullanıcı senaryolarında, bağımsız testlerle "
            "ölçer ve tek bir denetim raporu üretir."
        )
    )
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=PROJECT_ROOT / "workspace" / "real-world",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=PROJECT_ROOT / "data" / "real-world-arena.db",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "real-world-reports",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=EXTENDED_SCENARIOS,
        help="Seçili senaryoyu çalıştırır; birden fazla kez verilebilir.",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Hızlı üç senaryo yerine bütün Arena kataloğunu çalıştırır.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "Yerel model başarısız olursa ücretsiz uzak rotalara izin verir. "
            "Varsayılan tamamen yereldir."
        ),
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    args.project = args.project.resolve()
    args.workspace_root = args.workspace_root.resolve()
    args.history = args.history.resolve()
    args.report_dir = args.report_dir.resolve()
    return args


if __name__ == "__main__":
    _configure_console()
    raise SystemExit(asyncio.run(_run(_parse_args())))
