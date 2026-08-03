from __future__ import annotations

from collections import Counter
from typing import Any


_SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _integer(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    return str(value or "").strip()


def _verification_failures(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _items(payload.get("verifications"))
        if not bool(item.get("success"))
    ]


def _task_statuses(payload: dict[str, Any]) -> Counter[str]:
    return Counter(
        _text(task.get("status")) or "unknown"
        for task in _items(payload.get("tasks"))
    )


def _failure_kinds(payload: dict[str, Any]) -> Counter[str]:
    kinds: Counter[str] = Counter()
    for task in _items(payload.get("tasks")):
        for failure in _items(task.get("failure_history")):
            kind = _text(failure.get("kind")) or "unknown"
            kinds[kind] += max(1, _integer(failure.get("count"), 1))
    return kinds


def _event_types(payload: dict[str, Any]) -> Counter[str]:
    raw_counts = payload.get("event_counts")
    if isinstance(raw_counts, dict):
        counts: Counter[str] = Counter()
        for key, value in raw_counts.items():
            event_type = _text(key)
            if event_type:
                counts[event_type] = max(0, _integer(value))
        if counts:
            return counts
    return Counter(
        _text(event.get("type")) or "unknown"
        for event in _items(payload.get("last_events"))
    )


def _finding(
    *,
    code: str,
    severity: str,
    title: str,
    summary: str,
    evidence: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "summary": summary,
        "evidence": evidence,
        "next_action": next_action,
    }


def diagnose_arena_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic, read-only failure analysis for one Arena run."""

    run_id = _text(payload.get("run_id"))
    scenario_id = _text(payload.get("scenario_id"))
    status = _text(payload.get("status")) or "unknown"
    failure_reason = _text(payload.get("failure_reason"))
    missing_paths = [
        _text(item)
        for item in payload.get("missing_required_paths", [])
        if _text(item)
    ] if isinstance(payload.get("missing_required_paths"), list) else []
    changed_protected = [
        _text(item)
        for item in payload.get("changed_protected_paths", [])
        if _text(item)
    ] if isinstance(payload.get("changed_protected_paths"), list) else []
    failed_verifications = _verification_failures(payload)
    task_statuses = _task_statuses(payload)
    failure_kinds = _failure_kinds(payload)
    event_types = _event_types(payload)
    usage = _mapping(payload.get("usage"))
    failed_calls = _integer(usage.get("failed_calls"))
    task_attempts = _integer(payload.get("task_attempts"))
    failure_records = _integer(payload.get("failure_records"))

    retry_scheduled = event_types.get("focused_provider_retry_scheduled", 0)
    retry_exhausted = event_types.get("focused_provider_retry_exhausted", 0)
    provider_timeout_count = (
        failure_kinds.get("focused_provider_timeout", 0)
        + failure_kinds.get("provider_timeout", 0)
    )

    findings: list[dict[str, Any]] = []

    if changed_protected or payload.get("protected_paths_ok") is False:
        findings.append(
            _finding(
                code="scope_violation",
                severity="critical",
                title="Korunan dosya sınırı ihlal edildi",
                summary=(
                    "Koşu, senaryonun değiştirilmemesini istediği dosyalara "
                    "dokundu. Testler geçse bile bu teslimat güvenilir sayılamaz."
                ),
                evidence=(
                    [f"Değişen korunan dosya: {path}" for path in changed_protected]
                    or ["protected_paths_ok=false"]
                ),
                next_action=(
                    "Planlayıcının exact_files kapsamını ve workspace_write "
                    "korumasını incele; protected path değişmeden koşuyu yeniden "
                    "doğrula."
                ),
            )
        )

    if missing_paths or payload.get("required_paths_ok") is False:
        findings.append(
            _finding(
                code="missing_artifacts",
                severity="high",
                title="Zorunlu teslimat dosyaları eksik",
                summary=(
                    "Görev akışı tamamlanmadan veya bağımlı görev açılmadan önce "
                    "koşu ilerlemesiz duruma girmiş olabilir."
                ),
                evidence=(
                    [f"Eksik dosya: {path}" for path in missing_paths]
                    or ["required_paths_ok=false"]
                ),
                next_action=(
                    "Eksik dosyayı üreten görevin bağımlılıklarını, task-scoped "
                    "doğrulamasını ve blocked→ready geçişini incele."
                ),
            )
        )

    if retry_exhausted or provider_timeout_count:
        severity = "high" if status != "completed" or retry_exhausted else "medium"
        findings.append(
            _finding(
                code=(
                    "provider_retry_exhausted"
                    if retry_exhausted or status != "completed"
                    else "provider_retry_recovered"
                ),
                severity=severity,
                title=(
                    "Provider retry sınırı tükendi"
                    if severity == "high"
                    else "Geçici provider hatasından toparlandı"
                ),
                summary=(
                    "Focused üretim sırasında geçici provider/timeout hatası "
                    "gözlendi."
                ),
                evidence=[
                    f"provider timeout kaydı: {provider_timeout_count}",
                    f"retry scheduled: {retry_scheduled}",
                    f"retry exhausted: {retry_exhausted}",
                    f"başarısız model çağrısı: {failed_calls}",
                ],
                next_action=(
                    "Retry tükendiyse provider sağlık/timeout ayarlarını ve "
                    "remote fallback rotasını incele; toparlandıysa aynı senaryoyu "
                    "karşılaştırma ekranında maliyet ve süre açısından izle."
                ),
            )
        )
    elif retry_scheduled or failed_calls:
        findings.append(
            _finding(
                code="provider_instability",
                severity="medium" if status != "completed" else "low",
                title="Model sağlayıcısında geçici kararsızlık",
                summary=(
                    "Koşu sırasında başarısız model çağrısı veya retry olayı "
                    "kaydedildi."
                ),
                evidence=[
                    f"retry scheduled: {retry_scheduled}",
                    f"başarısız model çağrısı: {failed_calls}",
                ],
                next_action=(
                    "Provider bazlı kullanım kaydını ve son olayları kontrol et; "
                    "tekrarlanıyorsa ilgili rotayı geçici olarak düşür veya timeout "
                    "nedenini ölç."
                ),
            )
        )

    deterministic_repairs = event_types.get(
        "deterministic_contract_repair_selected",
        0,
    )
    if deterministic_repairs:
        findings.append(
            _finding(
                code="deterministic_contract_repair",
                severity="low" if status == "completed" else "medium",
                title="Deterministik sözleşme onarımı kullanıldı",
                summary=(
                    "Pytest sözleşmesindeki tek anlamlı fark model çağrısı "
                    "yerine güvenli ve deterministik bir onarım yoluyla ele "
                    "alındı."
                ),
                evidence=[
                    f"seçilen deterministik onarım: {deterministic_repairs}",
                ],
                next_action=(
                    "Notable event kanıtındaki path ve changes alanlarını "
                    "incele; aynı sözleşme farkı tekrarlanıyorsa üretim "
                    "promptunu iyileştir."
                ),
            )
        )

    blocked_count = task_statuses.get("blocked", 0)
    rework_count = task_statuses.get("rework_required", 0)
    if blocked_count or rework_count:
        findings.append(
            _finding(
                code="task_flow_blocked",
                severity="high" if status != "completed" else "medium",
                title="Görev akışı tamamlanmadan bloklandı",
                summary=(
                    "Bir veya daha fazla görev blocked ya da rework_required "
                    "durumunda kaldı."
                ),
                evidence=[
                    f"blocked görev: {blocked_count}",
                    f"rework_required görev: {rework_count}",
                    f"toplam task attempt: {task_attempts}",
                ],
                next_action=(
                    "İlk tamamlanmayan görevin dependency, recovery_reason ve "
                    "failure_history alanlarını incele; çalıştırılabilir görev "
                    "seçiminin ilerlemesiz duruma düşmediğini doğrula."
                ),
            )
        )

    if failed_verifications:
        names = [
            _text(item.get("name") or item.get("preset")) or "isimsiz doğrulama"
            for item in failed_verifications
        ]
        findings.append(
            _finding(
                code="verification_failure",
                severity="high",
                title="Bağımsız doğrulama başarısız",
                summary=(
                    "Arena'nın Supervisor'dan bağımsız çalıştırdığı en az bir "
                    "doğrulama geçmedi."
                ),
                evidence=[f"Başarısız doğrulama: {name}" for name in names],
                next_action=(
                    "İlk başarısız doğrulamanın output ve exit_code değerini "
                    "incele; task-scoped test ile nihai teslimat testinin doğru "
                    "aşamalarda çalıştığını doğrula."
                ),
            )
        )

    if status != "completed" and failure_reason:
        findings.append(
            _finding(
                code="run_failure_reason",
                severity="high",
                title="Koşu açık bir hata nedeni ile durdu",
                summary=failure_reason,
                evidence=[f"status={status}", f"failure_reason={failure_reason}"],
                next_action=(
                    "Failure reason ile son event zincirini birlikte incele ve "
                    "ilk kök neden düzeltilmeden aynı canlı koşuyu tekrarlama."
                ),
            )
        )

    if status == "completed" and not findings:
        findings.append(
            _finding(
                code="healthy_delivery",
                severity="info",
                title="Teslimat sağlıklı tamamlandı",
                summary=(
                    "Zorunlu dosyalar, korunan path'ler ve bağımsız doğrulamalar "
                    "açısından belirgin bir sorun bulunmadı."
                ),
                evidence=[
                    f"completed görev: {task_statuses.get('completed', 0)}",
                    f"başarısız doğrulama: {len(failed_verifications)}",
                    f"failure record: {failure_records}",
                ],
                next_action=(
                    "Aynı senaryonun önceki koşusuyla karşılaştırarak model çağrısı, "
                    "token ve süreyi düşürmeye odaklan."
                ),
            )
        )

    findings.sort(
        key=lambda item: (
            -_SEVERITY_ORDER.get(str(item.get("severity")), 0),
            str(item.get("code")),
        )
    )
    primary = findings[0]
    if status == "completed":
        health = "healthy" if primary["severity"] == "info" else "warning"
    else:
        health = "failed"

    recommendations: list[str] = []
    for finding in findings:
        action = _text(finding.get("next_action"))
        if action and action not in recommendations:
            recommendations.append(action)

    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "status": status,
        "health": health,
        "primary_issue": primary,
        "findings": findings,
        "recommendations": recommendations,
        "signals": {
            "missing_required_paths": missing_paths,
            "changed_protected_paths": changed_protected,
            "failed_verifications": len(failed_verifications),
            "task_statuses": dict(sorted(task_statuses.items())),
            "failure_kinds": dict(sorted(failure_kinds.items())),
            "event_types": dict(sorted(event_types.items())),
            "failed_model_calls": failed_calls,
            "task_attempts": task_attempts,
            "failure_records": failure_records,
        },
    }
