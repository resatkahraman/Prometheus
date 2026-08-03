import re

from app.planning.models import (
    PlanEvidence,
    PlanTask,
    PlanningDocument,
)
from app.planning.normalizer import normalize_planning_markdown


class PlanningParseError(ValueError):
    pass


_TASK_HEADER = re.compile(
    r"^###\s+(TASK-\d{3})\s+[—-]\s+(.+?)\s*$",
    flags=re.IGNORECASE,
)

_FIELD = re.compile(
    r"^(Seviye|Atanan Agent|Kanıt|Bağımlılıklar|"
    r"Bağımlılık Gerekçesi|Paralel Çalışabilir|"
    r"Doğrulama|Kullanıcı Onayı|Kesin Dosyalar)\s*:\s*(.*?)\s*$",
    flags=re.IGNORECASE,
)

_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


def _normalized_key(value: str) -> str:
    return (
        value.casefold()
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def _parse_bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        match = _BULLET.match(line)
        if match:
            items.append(match.group(1).strip())
    return items


_EVIDENCE_TOKEN = re.compile(
    r"(?P<kind>"
    r"file|dosya|user_request|kullanici_istegi|"
    r"verified_gap|dogrulanmis_eksik|assumption|varsayim"
    r")\s*:",
    flags=re.IGNORECASE,
)


def _parse_evidence(value: str) -> list[PlanEvidence]:
    text = value.strip()
    matches = list(_EVIDENCE_TOKEN.finditer(text))
    if not matches:
        raise PlanningParseError(
            "Kanıt alanı 'file:<yol>', 'user_request:<açıklama>', "
            "'verified_gap:<açıklama>' veya 'assumption:<açıklama>' "
            "biçiminde olmalıdır."
        )

    aliases = {
        "file": "file",
        "dosya": "file",
        "user_request": "user_request",
        "kullanici_istegi": "user_request",
        "verified_gap": "verified_gap",
        "dogrulanmis_eksik": "verified_gap",
        "assumption": "assumption",
        "varsayim": "assumption",
    }

    evidence: list[PlanEvidence] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        detail = text[start:end].strip(" \t\r\n,;")
        kind = aliases.get(_normalized_key(match.group("kind")))
        if kind is None:
            raise PlanningParseError(
                f"Bilinmeyen kanıt türü: {match.group('kind')}"
            )
        if not detail:
            raise PlanningParseError("Kanıt açıklaması boş olamaz.")
        evidence.append(PlanEvidence(type=kind, value=detail))

    return evidence


def _split_csv(value: str) -> list[str]:
    if value.strip().casefold() in {"yok", "none", "-"}:
        return []
    return [
        item.strip()
        for item in re.split(r"[,;]", value)
        if item.strip()
    ]


def parse_planning_document(
    text: str,
    *,
    max_tasks: int = 24,
) -> PlanningDocument:
    if not isinstance(text, str) or not text.strip():
        raise PlanningParseError("Plan metni boş.")

    text = normalize_planning_markdown(text)
    lines = text.splitlines()
    section_name: str | None = None
    sections: dict[str, list[str]] = {
        "facts": [],
        "assumptions": [],
        "decisions": [],
    }
    tasks: list[PlanTask] = []

    index = 0
    while index < len(lines):
        line = lines[index].strip()

        section_match = _SECTION.match(line)
        if section_match and not line.startswith("###"):
            title = _normalized_key(section_match.group(1))
            if "dogrulanmis proje gercek" in title:
                section_name = "facts"
            elif "varsayim" in title:
                section_name = "assumptions"
            elif "kritik kullanici karar" in title:
                section_name = "decisions"
            elif "gorev" in title:
                section_name = "tasks"
            else:
                section_name = None
            index += 1
            continue

        task_match = _TASK_HEADER.match(line)
        if task_match:
            if len(tasks) >= max_tasks:
                raise PlanningParseError(
                    f"Plan en fazla {max_tasks} görev içerebilir."
                )

            task_id = task_match.group(1).upper()
            title = task_match.group(2).strip()
            fields: dict[str, str] = {}
            criteria: list[str] = []
            index += 1
            reading_criteria = False

            while index < len(lines):
                current = lines[index].strip()
                if _TASK_HEADER.match(current) or (
                    _SECTION.match(current)
                    and not current.startswith("###")
                ):
                    break

                if re.match(
                    r"^Kabul Kriterleri\s*:\s*$",
                    current,
                    flags=re.IGNORECASE,
                ):
                    reading_criteria = True
                    index += 1
                    continue

                field_match = _FIELD.match(current)
                if field_match:
                    reading_criteria = False
                    fields[_normalized_key(field_match.group(1))] = (
                        field_match.group(2).strip()
                    )
                    index += 1
                    continue

                bullet_match = _BULLET.match(current)
                if bullet_match and reading_criteria:
                    criteria.append(bullet_match.group(1).strip())

                index += 1

            required = {
                "seviye",
                "atanan agent",
                "kanit",
                "bagimliliklar",
                "bagimlilik gerekcesi",
                "paralel calisabilir",
                "dogrulama",
                "kullanici onayi",
            }
            missing = sorted(required - set(fields))
            if missing:
                raise PlanningParseError(
                    f"{task_id} eksik alanlar: {', '.join(missing)}"
                )
            if not criteria:
                raise PlanningParseError(
                    f"{task_id} en az bir kabul kriteri içermelidir."
                )

            priority = _normalized_key(fields["seviye"])
            priority_alias = {
                "zorunlu": "zorunlu",
                "onerilen": "önerilen",
                "opsiyonel": "opsiyonel",
            }
            if priority not in priority_alias:
                raise PlanningParseError(
                    f"{task_id} geçersiz Seviye: {fields['seviye']}"
                )

            parallel = _normalized_key(fields["paralel calisabilir"])
            parallel_alias = {
                "evet": "evet",
                "hayir": "hayır",
            }
            if parallel not in parallel_alias:
                raise PlanningParseError(
                    f"{task_id} Paralel Çalışabilir 'evet' veya 'hayır' olmalı."
                )

            approval = _normalized_key(fields["kullanici onayi"])
            approval_alias = {
                "gerekmez": "gerekmez",
                "gerekli": "gerekli",
            }
            if approval not in approval_alias:
                raise PlanningParseError(
                    f"{task_id} Kullanıcı Onayı 'gerekmez' veya 'gerekli' olmalı."
                )

            exact_files = _split_csv(
                fields.get("kesin dosyalar", "yok")
            )

            tasks.append(
                PlanTask(
                    id=task_id,
                    title=title,
                    priority=priority_alias[priority],
                    assigned_agent=fields["atanan agent"].strip().casefold(),
                    evidence=_parse_evidence(fields["kanit"]),
                    acceptance_criteria=criteria,
                    dependencies=[
                        item.upper()
                        for item in _split_csv(fields["bagimliliklar"])
                    ],
                    dependency_reason=fields[
                        "bagimlilik gerekcesi"
                    ].strip(),
                    parallelizable=parallel_alias[parallel],
                    verification=fields["dogrulama"].strip(),
                    user_approval=approval_alias[approval],
                    exact_files=exact_files,
                )
            )
            continue

        if section_name in sections:
            sections[section_name].append(lines[index])

        index += 1

    if not tasks:
        raise PlanningParseError(
            "Plan, '### TASK-001 — Başlık' biçiminde görev içermiyor."
        )

    return PlanningDocument(
        verified_facts=_parse_bullets(sections["facts"]),
        assumptions=_parse_bullets(sections["assumptions"]),
        tasks=tasks,
        critical_decisions=_parse_bullets(sections["decisions"]),
    )
