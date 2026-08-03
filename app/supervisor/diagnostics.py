from __future__ import annotations

import json
import re
from typing import Any

from app.supervisor.models import SupervisorCommand


_SECRET = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if any(
                token in str(key).casefold()
                for token in (
                    "api_key",
                    "apikey",
                    "authorization",
                    "password",
                    "secret",
                )
            ):
                result[str(key)] = "***"
            else:
                result[str(key)] = _safe(item)
        return result
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        return _SECRET.sub(r"\1\2***", value)
    return value


def _json(value: Any) -> str:
    return json.dumps(
        _safe(value),
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def build_command_diagnostics(
    command: SupervisorCommand,
    *,
    adam_version: str = "0.8.0",
) -> str:
    lines: list[str] = [
        "PROMETHEUS TANILAMA RAPORU",
        "=" * 72,
        f"Prometheus sürümü: {adam_version}",
        f"Komut kimliği: {command.id}",
        f"Durum: {command.status}",
        f"Otomatik misyon: {command.auto_run}",
        f"Hedef: {command.goal}",
        f"Oluşturulma: {command.created_at}",
        f"Güncellenme: {command.updated_at}",
        "",
        "AKTİF İŞLEM",
        "-" * 72,
        f"İşlem: {command.active_operation or 'yok'}",
        f"Aşama: {command.operation_phase or 'yok'}",
        f"Mesaj: {command.operation_message or 'yok'}",
        f"Rota: {command.operation_route or 'yok'}",
        f"Hata: {command.failure_reason or 'yok'}",
        "",
        "GÖREVLER",
        "-" * 72,
    ]

    for task in command.tasks:
        lines.extend(
            [
                f"{task.id} — {task.title}",
                f"  Durum: {task.status}",
                f"  Agent: {task.assigned_agent}",
                f"  Deneme: {task.attempts}",
                f"  Continuation resume: {task.continuation_resumes}",
                f"  Recovery reason: {task.recovery_reason or 'yok'}",
                f"  Otonomi izni: {task.autonomy_granted}",
                (
                    "  Ortam revizyonu: "
                    f"{task.environment_revision} "
                    "(son değişiklik onayı: "
                    f"{task.last_environment_change_version or 'yok'})"
                ),
                (
                    "  Terminal runtime: "
                    f"{task.terminal_runtime_revision or 'legacy'}"
                ),
                (
                    "  Dosya üretim protokolü: "
                    f"{task.focused_generation_revision or 'legacy-json'}"
                ),
                (
                    "  Engelli durum imzası: "
                    f"{task.blocked_state_token or 'yok'}"
                ),
                f"  Döngü engeli: {task.blocked_reason or 'yok'}",
                f"  Hata imzaları: {len(task.failure_counts)}",
                (
                    "  Eksik kesin dosyalar: "
                    + (
                        ", ".join(task.reconciliation_missing_files)
                        or "yok"
                    )
                ),
                (
                    "  Materyalize edilen dosyalar: "
                    + (
                        ", ".join(task.materialized_files)
                        or "yok"
                    )
                ),
                (
                    "  Başarılı doğrulama kanıtı: "
                    + (
                        "var"
                        if task.reconciliation_verification_found
                        else "yok"
                    )
                ),
                (
                    "  Gerçek başarılı doğrulama: "
                    + (task.effective_verification or "yok")
                ),
                (
                    "  Doğrulama stratejisi: "
                    + (task.verification_strategy or "yok")
                ),
                (
                    "  Onay: "
                    f"state={task.approval_state}, "
                    f"version={task.approval_version}, "
                    f"tool={task.approval_tool or 'yok'}"
                ),
                f"  Onay mesajı: {task.last_approval_message or 'yok'}",
                f"  Agent cevabı: {task.last_answer or 'yok'}",
                f"  Reviewer: {task.review_answer or 'yok'}",
            ]
        )

        if task.approval_history:
            lines.append("  Onay geçmişi:")
            for record in task.approval_history:
                lines.extend(
                    [
                        (
                            f"    #{record.version} "
                            f"{record.tool or 'işlem'} — {record.state}"
                        ),
                        f"      Açıklama: {record.description or 'yok'}",
                        f"      Mesaj: {record.message or 'yok'}",
                        f"      Parmak izi: {record.fingerprint or 'yok'}",
                        f"      Argümanlar: {_json(record.arguments)}",
                        f"      Önizleme: {_json(record.preview)}",
                        f"      Başarı: {record.success}",
                        f"      Sonuç: {_json(record.result)}",
                    ]
                )

        response = task.last_agent_response
        if response is not None:
            lines.extend(
                [
                    "  Son agent teknik bilgisi:",
                    f"    Status: {response.status}",
                    f"    Route: {response.final_route or 'yok'}",
                    f"    Provider: {response.final_provider or 'yok'}",
                    f"    Model: {response.final_model or 'yok'}",
                    f"    Steps: {response.steps_used}",
                    f"    Model calls: {response.model_calls_used}",
                    f"    Tools: {', '.join(response.tools_used) or 'yok'}",
                ]
            )
            if response.trace:
                lines.append("    Trace:")
                for step in response.trace:
                    lines.extend(
                        [
                            (
                                f"      step={step.step} "
                                f"action={step.action} "
                                f"route={step.selected_route}"
                            ),
                            f"        reason={step.reason or 'yok'}",
                            f"        tool={step.tool or 'yok'}",
                            f"        arguments={_json(step.arguments)}",
                            f"        result={_json(step.tool_result)}",
                            f"        raw={step.raw_output or 'yok'}",
                        ]
                    )
        lines.append("")

    lines.extend(
        [
            "OLAY AKIŞI",
            "-" * 72,
        ]
    )
    for event in command.events[-100:]:
        lines.append(
            f"[{event.sequence}] {event.created_at} "
            f"{event.type} task={event.task_id or '-'}"
        )
        lines.append(f"  {event.message}")
        if event.data:
            lines.append(f"  data={_json(event.data)}")

    lines.extend(
        [
            "",
            "PLAN",
            "-" * 72,
            command.plan_text or "Plan yok.",
        ]
    )
    return str(_safe("\n".join(lines)))
