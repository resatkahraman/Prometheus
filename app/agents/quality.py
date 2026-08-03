import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.delivery import inspect_delivery_status
from app.agents.execution_evidence import inspect_execution_evidence
from app.agents.models import AgentProfile
from app.planning.integrity import validate_planning_document
from app.planning.parser import PlanningParseError, parse_planning_document


@dataclass(frozen=True)
class AgentQualityResult:
    accepted: bool
    reason: str
    warnings: list[str] = field(default_factory=list)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _missing_contract(
    answer: str,
    requirements: list[tuple[str, str]],
) -> list[str]:
    return [
        label
        for label, pattern in requirements
        if not _has(answer, pattern)
    ]


def inspect_agent_answer(
    *,
    profile: AgentProfile,
    answer: str,
    user_text: str,
    known_paths: set[str] | None = None,
    known_agents: set[str] | None = None,
    trace: list[Any] | None = None,
    planning_max_tasks: int = 24,
    planning_integrity_strict: bool = True,
    delivery_status_guard_enabled: bool = True,
    execution_evidence_guard_enabled: bool = True,
) -> AgentQualityResult:
    if not isinstance(answer, str) or not answer.strip():
        return AgentQualityResult(False, "Final cevap boş.")

    normalized = _normalized(answer)

    vague_completion = _has(
        normalized,
        r"\b(hazırlandı|tanımlandı|tamamlandı|oluşturuldu)\b",
    )
    has_delivery_structure = (
        "\n" in answer
        or ":" in answer
        or _has(answer, r"\b(1[.)]|2[.)]|görev\s*\d+|task\s*\d+)\b")
    )
    report_agents = {"planner", "architect", "reviewer", "qa"}
    if (
        profile.id in report_agents
        and len(normalized) < 120
        and vague_completion
        and not has_delivery_structure
    ):
        return AgentQualityResult(
            False,
            "Agent işi yaptığını söyledi fakat somut çıktıyı teslim etmedi.",
        )

    if profile.id == "planner" and planning_integrity_strict:
        try:
            document = parse_planning_document(
                answer,
                max_tasks=planning_max_tasks,
            )
        except PlanningParseError as exc:
            return AgentQualityResult(
                False,
                f"Plan biçimi ayrıştırılamadı: {exc}",
            )

        integrity = validate_planning_document(
            document,
            known_paths=known_paths,
            known_agents=known_agents,
        )
        if not integrity.valid:
            return AgentQualityResult(
                False,
                "Plan bütünlük hataları: " + " | ".join(integrity.errors),
                warnings=integrity.warnings,
            )

        return AgentQualityResult(
            True,
            "Plan yapısal ve mühendislik bütünlüğü kontrolünü geçti.",
            warnings=integrity.warnings,
        )

    role_requirements: dict[str, list[tuple[str, str]]] = {
        "architect": [
            ("mevcut durum", r"mevcut durum|mevcut mimari|current state"),
            ("mimari yapı", r"mimari|architecture|modül|katman"),
            ("riskler", r"risk"),
            ("önerilen yapı", r"önerilen|hedef mimari|yeni yapı|recommend"),
            ("doğrulama/geçiş planı", r"doğrulama|geçiş|uygulama sırası|test plan"),
        ],
        "reviewer": [
            ("kabul veya ret kararı", r"\b(kabul|ret|approve|reject)\b"),
            ("kanıt", r"kanıt|evidence|diff|test sonucu|exit code"),
            ("sorunlar", r"sorun|bulgu|issue|risk"),
            ("yeniden çalışma", r"yeniden çalışma|rework|düzeltme görevi"),
        ],
        "qa": [
            ("test senaryoları", r"test senaryo|test case|testler"),
            ("gerçek sonuç", r"exit code|başarılı|başarısız|passed|failed"),
        ],
    }

    requirements = role_requirements.get(profile.id)
    if requirements:
        minimum_length = 220 if profile.id == "architect" else 140
        if len(normalized) < minimum_length:
            return AgentQualityResult(
                False,
                f"{profile.name} cevabı rol sözleşmesi için çok kısa.",
            )

        missing = _missing_contract(answer, requirements)
        if missing:
            return AgentQualityResult(
                False,
                "Eksik zorunlu bölümler: " + ", ".join(missing) + ".",
            )

    if profile.id == "calculation":
        if not _has(
            answer,
            r"sonuç|türev|integral|çözüm|sadeleştiril|result|derivative",
        ):
            return AgentQualityResult(
                False,
                "Calculation cevabı hesap sonucunu açıkça göstermiyor.",
            )

    if execution_evidence_guard_enabled:
        evidence = inspect_execution_evidence(
            user_text=user_text,
            answer=answer,
            trace=trace,
        )
        if not evidence.accepted:
            return AgentQualityResult(False, evidence.reason)

    if delivery_status_guard_enabled:
        delivery = inspect_delivery_status(
            agent_id=profile.id,
            answer=answer,
            trace=trace,
        )
        if not delivery.accepted:
            return AgentQualityResult(False, delivery.reason)

    return AgentQualityResult(True, "Rol çıktı sözleşmesi karşılandı.")
