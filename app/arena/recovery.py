from __future__ import annotations

import re
from typing import Any

from app.arena.diagnostics import diagnose_arena_run


_SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _text(value: object) -> str:
    return str(value or "").strip()


def _finding_codes(diagnosis: dict[str, Any]) -> set[str]:
    findings = diagnosis.get("findings")
    if not isinstance(findings, list):
        return set()
    return {
        _text(item.get("code"))
        for item in findings
        if isinstance(item, dict) and _text(item.get("code"))
    }


def _step(
    order: int,
    *,
    code: str,
    title: str,
    detail: str,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "order": order,
        "code": code,
        "title": title,
        "detail": detail,
        "required": required,
    }


def build_arena_recovery_plan(
    payload: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
    *,
    known_scenarios: set[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, non-executing recovery manifest for one run."""

    diagnosis = diagnosis or diagnose_arena_run(payload)
    run_id = _text(payload.get("run_id"))
    scenario_id = _text(payload.get("scenario_id"))
    status = _text(payload.get("status")) or "unknown"
    health = _text(diagnosis.get("health")) or "unknown"
    codes = _finding_codes(diagnosis)

    scenario_is_safe = bool(_SCENARIO_ID_PATTERN.fullmatch(scenario_id))
    scenario_is_known = (
        scenario_is_safe
        and (
            known_scenarios is None
            or scenario_id in known_scenarios
        )
    )
    scope_blocked = "scope_violation" in codes
    completed = status == "completed"
    recovered_warning = completed and (
        "provider_retry_recovered" in codes
        or "provider_instability" in codes
    )

    if completed and health == "healthy":
        decision = "not_required"
        strategy = "no_action"
        title = "Kurtarma gerekmiyor"
        summary = (
            "Koşu sağlıklı tamamlandı. Yeni bir canlı koşu yerine aynı "
            "senaryonun önceki sonucu ile kalite ve maliyet karşılaştırması yap."
        )
        rerun_recommended = False
    elif recovered_warning:
        decision = "optional"
        strategy = "compare_before_rerun"
        title = "Teslimat toparlandı; yeniden koşu isteğe bağlı"
        summary = (
            "Koşu geçici provider hatasına rağmen tamamlandı. Yeniden koşu "
            "zorunlu değildir; önce süre, token ve başarısız çağrı farklarını "
            "karşılaştır."
        )
        rerun_recommended = False
    elif scope_blocked:
        decision = "blocked"
        strategy = "manual_scope_review"
        title = "Yeniden koşu korunan dosya ihlali nedeniyle bloklandı"
        summary = (
            "Aynı senaryoyu tekrar çalıştırmadan önce exact_files, protected "
            "paths ve workspace_write sınırı düzeltilmelidir."
        )
        rerun_recommended = False
    elif status != "completed" and scenario_is_known:
        decision = "ready_for_approval"
        strategy = "fresh_scenario_rerun"
        title = "Temiz çalışma alanında tek seferlik yeniden koşu hazırlanabilir"
        summary = (
            "Koşu başarısız oldu ancak kayıtlı senaryo yeniden üretilebilir. "
            "Önceki kanıt korunarak yeni workspace, history ve log yollarında "
            "yalnızca bir canlı koşu yapılmalıdır."
        )
        rerun_recommended = True
    else:
        decision = "blocked"
        strategy = "manual_investigation"
        title = "Otomatik yeniden koşu planı oluşturulamadı"
        summary = (
            "Koşu tamamlanmadı ancak senaryo kimliği kayıtlı ve güvenli bir "
            "Arena senaryosu olarak doğrulanamadı."
        )
        rerun_recommended = False

    execution_available = (
        decision == "ready_for_approval"
        and scenario_is_known
        and not scope_blocked
    )
    approval_phrase = (
        f"ARENA RERUN {scenario_id} FROM {run_id}"
        if execution_available
        else None
    )
    command_preview = (
        "python scripts/run_prometheus_arena.py "
        f"--scenario {scenario_id} --live"
        if execution_available
        else None
    )

    steps: list[dict[str, Any]] = []
    if decision == "ready_for_approval":
        steps = [
            _step(
                1,
                code="preserve_evidence",
                title="Önceki kanıtı koru",
                detail=(
                    "Kaynak run workspace, Arena result JSON, history DB ve log "
                    "dosyalarını değiştirme veya silme."
                ),
            ),
            _step(
                2,
                code="quota_preflight",
                title="Ücretsiz kota preflight çalıştır",
                detail=(
                    "Canlı model çağrısından önce senaryonun minimum çağrı "
                    "gereksinimi ve koruma payı doğrulanmalı."
                ),
            ),
            _step(
                3,
                code="fresh_output_paths",
                title="Yeni çıktı yolları ayır",
                detail=(
                    "Yeni ve boş workspace, history ve log yolları kullan; eski "
                    "koşunun çalışma alanını devam ettirme."
                ),
            ),
            _step(
                4,
                code="explicit_approval",
                title="Kullanıcı onayı al",
                detail=(
                    "Canlı koşu yalnızca tam onay cümlesi kullanıcı tarafından "
                    "verildikten sonra başlatılabilir."
                ),
            ),
            _step(
                5,
                code="single_live_run",
                title="Senaryoyu yalnızca bir kez çalıştır",
                detail=(
                    "Wrapper veya operatör seviyesinde retry yapma; ürünün kendi "
                    "sınırlı retry mekanizmasını yalnızca gözlemle."
                ),
            ),
            _step(
                6,
                code="compare_result",
                title="Yeni sonucu kaynak koşuyla karşılaştır",
                detail=(
                    "Başarı durumu, doğrulamalar, skor, token, model çağrısı ve "
                    "süre farklarını Arena karşılaştırma ekranında incele."
                ),
            ),
        ]
    elif decision == "blocked":
        steps = [
            _step(
                1,
                code="resolve_primary_issue",
                title="Birincil teşhisi çöz",
                detail=_text(
                    diagnosis.get("primary_issue", {}).get("next_action")
                    if isinstance(diagnosis.get("primary_issue"), dict)
                    else ""
                ) or "Teşhis kanıtlarını ve son olay zincirini incele.",
            ),
            _step(
                2,
                code="rebuild_plan",
                title="Düzeltmeden sonra recovery planını yeniden oluştur",
                detail=(
                    "Bloklayan neden çözülmeden canlı koşu başlatma; planın "
                    "ready_for_approval durumuna geçtiğini doğrula."
                ),
            ),
        ]
    else:
        steps = [
            _step(
                1,
                code="compare_history",
                title="Geçmiş koşularla karşılaştır",
                detail=(
                    "Yeni canlı koşu yerine aynı senaryonun kalite ve verimlilik "
                    "trendini karşılaştır."
                ),
                required=False,
            )
        ]

    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "status": status,
        "health": health,
        "decision": decision,
        "strategy": strategy,
        "title": title,
        "summary": summary,
        "rerun_recommended": rerun_recommended,
        "execution_available": execution_available,
        "requires_user_approval": execution_available,
        "approval_phrase": approval_phrase,
        "command_preview": command_preview,
        "steps": steps,
        "safeguards": {
            "preserve_source_run": True,
            "fresh_workspace_required": execution_available,
            "quota_preflight_required": execution_available,
            "one_live_invocation_only": execution_available,
            "manual_artifact_edits_forbidden": True,
            "protected_paths_must_remain_unchanged": True,
            "automatic_execution": False,
        },
        "source_diagnosis": {
            "primary_code": _text(
                diagnosis.get("primary_issue", {}).get("code")
                if isinstance(diagnosis.get("primary_issue"), dict)
                else ""
            ),
            "finding_codes": sorted(codes),
            "recommendations": list(diagnosis.get("recommendations") or []),
        },
    }
