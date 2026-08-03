from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def result_gates(payload: dict[str, Any]) -> dict[str, bool]:
    verifications = payload.get("verifications") or []
    coordination = payload.get("coordination") or {}
    return {
        "completed": payload.get("status") == "completed",
        "verification": bool(verifications)
        and all(item.get("success") is True for item in verifications),
        "required_paths": payload.get("required_paths_ok") is True,
        "protected_paths": payload.get("protected_paths_ok") is True,
        "work_sharing": coordination.get("work_sharing_ok", True) is True,
    }


def build_suite_report(
    results: Iterable[dict[str, Any]],
    *,
    started_at: str,
    finished_at: str | None = None,
    local_only: bool,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    total_calls = 0
    total_tokens = 0
    elapsed_seconds = 0.0

    for payload in results:
        usage = payload.get("usage") or {}
        gates = result_gates(payload)
        calls = int(usage.get("model_calls") or 0)
        tokens = int(usage.get("total_tokens") or 0)
        elapsed = float(payload.get("elapsed_seconds") or 0.0)
        total_calls += calls
        total_tokens += tokens
        elapsed_seconds += elapsed
        items.append(
            {
                "scenario": payload.get("scenario_id", "unknown"),
                "title": payload.get("scenario_title", ""),
                "passed": all(gates.values()),
                "gates": gates,
                "status": payload.get("status", "failed"),
                "failure_reason": payload.get("failure_reason"),
                "score": (payload.get("score") or {}).get("total", 0),
                "elapsed_seconds": round(elapsed, 2),
                "model_calls": calls,
                "total_tokens": tokens,
                "workspace": payload.get("workspace"),
            }
        )

    passed = sum(1 for item in items if item["passed"])
    completed_at = finished_at or datetime.now(timezone.utc).isoformat()
    return {
        "suite": "Prometheus real-world",
        "mode": "local-only" if local_only else "free-routes",
        "started_at": started_at,
        "finished_at": completed_at,
        "passed": passed,
        "failed": len(items) - passed,
        "total": len(items),
        "success": bool(items) and passed == len(items),
        "model_calls": total_calls,
        "total_tokens": total_tokens,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "results": items,
    }


def render_suite_markdown(report: dict[str, Any]) -> str:
    outcome = "BAŞARILI" if report["success"] else "BAŞARISIZ"
    lines = [
        "# Prometheus Real-World Test Raporu",
        "",
        f"- Sonuç: **{outcome}**",
        f"- Mod: `{report['mode']}`",
        f"- Senaryolar: {report['passed']}/{report['total']} geçti",
        f"- Model çağrısı: {report['model_calls']}",
        f"- Toplam token: {report['total_tokens']}",
        f"- Toplam süre: {report['elapsed_seconds']:.2f} saniye",
        "",
        "| Senaryo | Sonuç | Puan | Çağrı | Token | Süre |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["results"]:
        status = "GEÇTİ" if item["passed"] else "KALDI"
        lines.append(
            f"| `{item['scenario']}` | {status} | {item['score']} | "
            f"{item['model_calls']} | {item['total_tokens']} | "
            f"{item['elapsed_seconds']:.2f} sn |"
        )
        if item.get("failure_reason"):
            lines.extend(
                [
                    "",
                    f"**{item['scenario']} hata nedeni:** "
                    f"{item['failure_reason']}",
                ]
            )

    lines.extend(
        [
            "",
            "## Geçiş kapıları",
            "",
            "Her senaryo; görev tamamlama, bağımsız doğrulama, zorunlu "
            "dosyalar, korunan dosyalar ve gerekiyorsa gerçek iş paylaşımı "
            "kapılarının tamamından geçmek zorundadır.",
            "",
        ]
    )
    return "\n".join(lines)
