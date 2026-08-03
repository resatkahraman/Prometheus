from dataclasses import dataclass, field
from pathlib import PurePosixPath
import re

from app.planning.models import PlanTask, PlanningDocument


@dataclass(frozen=True)
class PlanningIntegrityResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_layers: list[list[str]] = field(default_factory=list)


_DELETE_TERMS = re.compile(
    r"\b(sil|silme|kaldır|kaldirma|delete|remove|cleanup|temizle)\w*",
    flags=re.IGNORECASE,
)
_TEST_TERMS = re.compile(
    r"\b(test|pytest|jest|vitest|birim test|integration test)\b",
    flags=re.IGNORECASE,
)
_FRONTEND_TERMS = re.compile(
    r"\b(react|tsx|jsx|component|bileşen|frontend|arayüz|ui|css)\b",
    flags=re.IGNORECASE,
)
_BACKEND_TERMS = re.compile(
    r"\b(api|backend|fastapi|flask|endpoint|servis|server)\b",
    flags=re.IGNORECASE,
)
_DATABASE_TERMS = re.compile(
    r"\b(database|veritabanı|veritabani|migration|schema|sql|prisma)\b",
    flags=re.IGNORECASE,
)
_INTEGRATION_TERMS = re.compile(
    r"\b(integration|entegrasyon|build|merge|birleştir)\w*",
    flags=re.IGNORECASE,
)
_GENERIC_DEPENDENCY = {
    "önce yapılmalı",
    "once yapilmali",
    "gerekli",
    "bu görevden sonra",
    "sıralama için",
    "siralama icin",
    "proje yapısının belirlenmesi gerekli",
    "proje yapisinin belirlenmesi gerekli",
    "önce proje yapısı incelenmeli",
    "once proje yapisi incelenmeli",
    "önce analiz edilmeli",
    "once analiz edilmeli",
}

_READ_ONLY_VERIFICATION = re.compile(
    r"^(workspace_read|workspace_list|project_summary|git_status)"
    r"(?:\s+aracı)?$",
    flags=re.IGNORECASE,
)

_WORKING_CLAIM = re.compile(
    r"\b(çalışır durumda|calisir durumda|çalışmalı|calismali|"
    r"works|working|işlevsel|islevsel)\b",
    flags=re.IGNORECASE,
)

_PLANNER_EXECUTION_TERMS = re.compile(
    r"\b(plan\w*|gereksinim\w*|requirement\w*|roadmap|yol haritası)\b",
    flags=re.IGNORECASE,
)


def _normalize_path(value: str) -> str:
    return PurePosixPath(
        value.strip().replace("\\", "/").lstrip("./")
    ).as_posix()


def _graph_layers(tasks: list[PlanTask]) -> tuple[list[list[str]], list[str]]:
    ids = {task.id for task in tasks}
    incoming = {
        task.id: {dependency for dependency in task.dependencies}
        for task in tasks
    }
    errors: list[str] = []

    for task_id, dependencies in incoming.items():
        unknown = sorted(dependencies - ids)
        if unknown:
            errors.append(
                f"{task_id} bilinmeyen bağımlılıklara sahip: "
                f"{', '.join(unknown)}."
            )
        if task_id in dependencies:
            errors.append(f"{task_id} kendisine bağımlı olamaz.")

    if errors:
        return [], errors

    remaining = {key: set(value) for key, value in incoming.items()}
    layers: list[list[str]] = []
    completed: set[str] = set()

    while remaining:
        ready = sorted(
            task_id
            for task_id, dependencies in remaining.items()
            if dependencies <= completed
        )
        if not ready:
            cycle_nodes = ", ".join(sorted(remaining))
            errors.append(
                "Görev bağımlılık grafiğinde döngü var: "
                f"{cycle_nodes}."
            )
            return layers, errors

        layers.append(ready)
        completed.update(ready)
        for task_id in ready:
            remaining.pop(task_id)

    return layers, errors


def _expected_agent(task: PlanTask) -> str | None:
    text = (
        task.title
        + " "
        + " ".join(task.acceptance_criteria)
        + " "
        + task.verification
    )
    if _TEST_TERMS.search(text):
        return "qa"
    if _DATABASE_TERMS.search(text):
        return "database"
    if _FRONTEND_TERMS.search(text):
        return "frontend"
    if _BACKEND_TERMS.search(text):
        return "backend"
    if _INTEGRATION_TERMS.search(text):
        return "integration"
    return None


def validate_planning_document(
    document: PlanningDocument,
    *,
    known_paths: set[str] | None = None,
    known_agents: set[str] | None = None,
) -> PlanningIntegrityResult:
    known_paths = {
        _normalize_path(path)
        for path in (known_paths or set())
        if path.strip()
    }
    known_agents = known_agents or set()

    errors: list[str] = []
    warnings: list[str] = []

    ids = [task.id for task in document.tasks]
    if len(ids) != len(set(ids)):
        errors.append("Görev kimlikleri benzersiz olmalıdır.")

    expected_ids = [
        f"TASK-{index:03d}"
        for index in range(1, len(document.tasks) + 1)
    ]
    if ids != expected_ids:
        errors.append(
            "Görev kimlikleri sıralı olmalıdır: "
            + ", ".join(expected_ids)
            + "."
        )

    layers, graph_errors = _graph_layers(document.tasks)
    errors.extend(graph_errors)

    for task in document.tasks:
        if known_agents and task.assigned_agent not in known_agents:
            errors.append(
                f"{task.id} bilinmeyen agente atanmış: "
                f"{task.assigned_agent}."
            )

        if (
            task.assigned_agent == "planner"
            and not _PLANNER_EXECUTION_TERMS.search(task.title)
        ):
            errors.append(
                f"{task.id} Planner'a icra/inceleme görevi atıyor. "
                "Planner plan üretir; teknik inceleme Architect veya "
                "Reviewer'a, uygulama işi ilgili worker agentına verilmelidir."
            )

        expected_agent = _expected_agent(task)
        if (
            expected_agent
            and task.assigned_agent not in {expected_agent, "worker"}
        ):
            warnings.append(
                f"{task.id} içeriği '{expected_agent}' agentına daha uygun, "
                f"ancak '{task.assigned_agent}' atanmış."
            )

        assumption_count = 0
        non_assumption_count = 0

        for evidence in task.evidence:
            if evidence.type == "file":
                evidence_path = _normalize_path(evidence.value)
                if known_paths and evidence_path not in known_paths:
                    errors.append(
                        f"{task.id} kanıt olarak bulunmayan dosyayı "
                        f"gösteriyor: {evidence.value}."
                    )
                else:
                    non_assumption_count += 1
            elif evidence.type == "assumption":
                assumption_count += 1
                warnings.append(
                    f"{task.id} varsayıma dayanıyor: {evidence.value}. "
                    "Uygulanmadan önce doğrulanmalı."
                )
            else:
                non_assumption_count += 1

        if (
            task.priority == "zorunlu"
            and assumption_count > 0
            and non_assumption_count == 0
        ):
            errors.append(
                f"{task.id} yalnızca varsayıma dayanırken 'zorunlu' olamaz."
            )

        if task.dependencies:
            reason_normalized = re.sub(
                r"\s+",
                " ",
                task.dependency_reason.casefold(),
            ).strip()
            if (
                len(reason_normalized) < 20
                or reason_normalized in _GENERIC_DEPENDENCY
            ):
                errors.append(
                    f"{task.id} bağımlılık gerekçesi teknik olarak "
                    "açıklayıcı değil."
                )
            if task.parallelizable == "evet":
                warnings.append(
                    f"{task.id} bağımlılık içeriyor; 'Paralel Çalışabilir: "
                    "evet' yalnızca bağımlılık tamamlandıktan sonraki "
                    "paralelliği ifade etmelidir."
                )
        else:
            if task.dependency_reason.casefold().strip() not in {
                "yok",
                "bağımlılık yok",
                "bagimlilik yok",
                "none",
            }:
                warnings.append(
                    f"{task.id} bağımlılığı yok fakat gerekçe alanı "
                    "gereksiz açıklama içeriyor."
                )
            if task.parallelizable == "hayır":
                warnings.append(
                    f"{task.id} bağımlılıksız olduğu hâlde paralel değil; "
                    "bunun planlayıcı tarafından gerekçelendirilmesi gerekir."
                )

        mutating_agent = task.assigned_agent in {
            "worker",
            "frontend",
            "backend",
            "database",
            "integration",
            "qa",
        }
        if (
            mutating_agent
            and task.user_approval == "gerekli"
            and not task.exact_files
        ):
            errors.append(
                f"{task.id} kod/çalışma alanı değişikliği istiyor fakat "
                "Kesin Dosyalar alanı boş. Belirsiz worker görevi "
                "çalıştırılamaz."
            )

        # Acceptance criteria describe application behaviour too (for example
        # a calculator's "temizle" and "geri silme" buttons). Treating those
        # words as workspace deletion corrupts otherwise valid repeated plans.
        # The task title is the authoritative operation intent.
        destructive = bool(_DELETE_TERMS.search(task.title))
        if destructive:
            if task.user_approval != "gerekli":
                errors.append(
                    f"{task.id} silme/temizleme içeriyor; kullanıcı onayı "
                    "zorunludur."
                )
            if not task.exact_files:
                errors.append(
                    f"{task.id} silme/temizleme içeriyor; 'Kesin Dosyalar' "
                    "alanı boş olamaz."
                )
            for path in task.exact_files:
                normalized = _normalize_path(path)
                if known_paths and normalized not in known_paths:
                    errors.append(
                        f"{task.id} silmek için bulunmayan dosyayı listeliyor: "
                        f"{path}."
                    )
        elif task.exact_files:
            warnings.append(
                f"{task.id} yıkıcı görev değil fakat Kesin Dosyalar alanı dolu."
            )

        if not task.verification.strip():
            errors.append(f"{task.id} doğrulama yöntemi içermiyor.")

        working_criteria = [
            criterion
            for criterion in task.acceptance_criteria
            if _WORKING_CLAIM.search(criterion)
        ]
        if (
            working_criteria
            and _READ_ONLY_VERIFICATION.match(task.verification.strip())
        ):
            errors.append(
                f"{task.id} çalışırlık iddia ediyor fakat yalnızca "
                f"'{task.verification}' ile doğrulama yapıyor. "
                "Çalışırlık için test, build, compile veya gerçek çalışma "
                "kanıtı gerekir."
            )

        vague_criteria = [
            criterion
            for criterion in task.acceptance_criteria
            if re.search(
                r"\b(uygun|başarılı şekilde|düzenli|iyi|doğru)\b",
                criterion,
                flags=re.IGNORECASE,
            )
            and not re.search(
                r"\b(test|exit code|dosya|endpoint|satır|build|"
                r"pytest|jest|lint|typecheck|diff)\b",
                criterion,
                flags=re.IGNORECASE,
            )
        ]
        if vague_criteria:
            errors.append(
                f"{task.id} ölçülemeyen kabul kriterleri içeriyor: "
                + " | ".join(vague_criteria)
            )

    if not document.verified_facts:
        errors.append("Doğrulanmış proje gerçekleri bölümü boş olamaz.")

    if not document.critical_decisions:
        warnings.append(
            "Kritik kullanıcı kararları boş; gerçekten karar yoksa "
            "'Yok' maddesi açıkça yazılmalı."
        )

    return PlanningIntegrityResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        execution_layers=layers,
    )
