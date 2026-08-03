from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ExecutionEvidenceResult:
    accepted: bool
    reason: str


_WRITE_INTENT = re.compile(
    r"\b("
    r"oluştur|olustur|yarat|create|"
    r"yaz|write|ekle|add|"
    r"değiştir|degistir|güncelle|guncelle|update|modify|"
    r"düzelt|duzelt|fix|patch|"
    r"sil|delete|remove"
    r")\w*",
    flags=re.IGNORECASE,
)

_FILE_REFERENCE = re.compile(
    r"(?P<path>"
    r"(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+"
    r"|[A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|json|yaml|yml|md|txt|"
    r"html|css|scss|java|kt|dart|sql|toml|ini)"
    r")",
    flags=re.IGNORECASE,
)

_COMPLETION_CLAIM = re.compile(
    r"\b("
    r"oluşturuldu|olusturuldu|oluşturdum|olusturdum|"
    r"yazıldı|yazildi|yazdım|yazdim|"
    r"eklendi|ekledim|"
    r"değiştirildi|degistirildi|değiştirdim|degistirdim|"
    r"güncellendi|guncellendi|güncelledim|guncelledim|"
    r"düzeltildi|duzeltildi|düzelttim|duzelttim|"
    r"silindi|sildim|"
    r"created|written|updated|modified|fixed|deleted"
    r")\b",
    flags=re.IGNORECASE,
)


def _successful_tool_steps(
    trace: list[Any] | None,
    tool_name: str,
) -> list[Any]:
    if not trace:
        return []

    steps: list[Any] = []
    for step in trace:
        if getattr(step, "tool", None) != tool_name:
            continue
        result = getattr(step, "tool_result", None)
        if not isinstance(result, dict):
            continue

        if tool_name == "workspace_write" and result.get("changed") is True:
            steps.append(step)
        elif tool_name == "safe_terminal" and result.get("success") is True:
            steps.append(step)

    return steps


def _normalize_path(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./").casefold()


def inspect_execution_evidence(
    *,
    user_text: str,
    answer: str,
    trace: list[Any] | None,
) -> ExecutionEvidenceResult:
    mutation_requested = bool(_WRITE_INTENT.search(user_text))
    requested_paths = {
        _normalize_path(match.group("path"))
        for match in _FILE_REFERENCE.finditer(user_text)
    }
    completion_claimed = bool(_COMPLETION_CLAIM.search(answer))

    successful_writes = _successful_tool_steps(trace, "workspace_write")
    written_paths = set()

    for step in successful_writes:
        result = getattr(step, "tool_result", None)
        if isinstance(result, dict) and result.get("path"):
            written_paths.add(_normalize_path(str(result["path"])))

    if mutation_requested and not successful_writes:
        return ExecutionEvidenceResult(
            False,
            "Kullanıcı dosya oluşturma/değiştirme/silme istedi fakat "
            "başarılı workspace_write kanıtı yok. Agent final vermek yerine "
            "uygun aracı çağırmalıdır.",
        )

    if completion_claimed and not successful_writes:
        return ExecutionEvidenceResult(
            False,
            "Final cevap dosya işleminin tamamlandığını iddia ediyor fakat "
            "trace içinde başarılı workspace_write kanıtı yok.",
        )

    if requested_paths and successful_writes:
        missing = sorted(requested_paths - written_paths)
        if missing:
            return ExecutionEvidenceResult(
                False,
                "Kullanıcının istediği dosyalar için yazma kanıtı eksik: "
                + ", ".join(missing)
                + ".",
            )

    if successful_writes and not completion_claimed:
        return ExecutionEvidenceResult(
            False,
            "workspace_write başarılı oldu fakat final cevap yapılan "
            "değişikliği açıkça teslim etmiyor.",
        )

    return ExecutionEvidenceResult(
        True,
        "Dosya işlemi iddiaları gerçek araç kanıtıyla uyumlu.",
    )
