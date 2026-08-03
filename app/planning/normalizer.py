import re


_TASK_HEADER = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[-*+]\s*)?(?:\*\*)?"
    r"(TASK-\d{3})"
    r"(?:\*\*)?\s*(?:[—–\-:])\s*(.+?)\s*$",
    flags=re.IGNORECASE,
)

_FIELD_ALIASES = {
    "seviye": "Seviye",
    "öncelik": "Seviye",
    "oncelik": "Seviye",
    "priority": "Seviye",
    "atanan agent": "Atanan Agent",
    "atanan uzman": "Atanan Agent",
    "agent": "Atanan Agent",
    "assigned agent": "Atanan Agent",
    "assignee": "Atanan Agent",
    "kanıt": "Kanıt",
    "kanit": "Kanıt",
    "evidence": "Kanıt",
    "kabul kriterleri": "Kabul Kriterleri",
    "kabul kriteri": "Kabul Kriterleri",
    "acceptance criteria": "Kabul Kriterleri",
    "acceptance criterion": "Kabul Kriterleri",
    "bağımlılıklar": "Bağımlılıklar",
    "bagimliliklar": "Bağımlılıklar",
    "dependencies": "Bağımlılıklar",
    "dependency": "Bağımlılıklar",
    "bağımlılık gerekçesi": "Bağımlılık Gerekçesi",
    "bagimlilik gerekcesi": "Bağımlılık Gerekçesi",
    "dependency reason": "Bağımlılık Gerekçesi",
    "paralel çalışabilir": "Paralel Çalışabilir",
    "paralel calisabilir": "Paralel Çalışabilir",
    "parallelizable": "Paralel Çalışabilir",
    "parallel": "Paralel Çalışabilir",
    "doğrulama": "Doğrulama",
    "dogrulama": "Doğrulama",
    "verification": "Doğrulama",
    "validation": "Doğrulama",
    "kullanıcı onayı": "Kullanıcı Onayı",
    "kullanici onayi": "Kullanıcı Onayı",
    "user approval": "Kullanıcı Onayı",
    "approval": "Kullanıcı Onayı",
    "kesin dosyalar": "Kesin Dosyalar",
    "exact files": "Kesin Dosyalar",
    "files": "Kesin Dosyalar",
}

_SECTION_ALIASES = {
    "doğrulanmış proje gerçekleri": "## Doğrulanmış Proje Gerçekleri",
    "dogrulanmis proje gercekleri": "## Doğrulanmış Proje Gerçekleri",
    "verified project facts": "## Doğrulanmış Proje Gerçekleri",
    "varsayımlar": "## Varsayımlar",
    "varsayimlar": "## Varsayımlar",
    "assumptions": "## Varsayımlar",
    "görevler": "## Görevler",
    "gorevler": "## Görevler",
    "tasks": "## Görevler",
    "kritik kullanıcı kararları": "## Kritik Kullanıcı Kararları",
    "kritik kullanici kararlari": "## Kritik Kullanıcı Kararları",
    "critical user decisions": "## Kritik Kullanıcı Kararları",
}

_VALUE_ALIASES = {
    "mandatory": "zorunlu",
    "required": "zorunlu",
    "recommended": "önerilen",
    "optional": "opsiyonel",
    "yes": "evet",
    "no": "hayır",
    "none": "yok",
    "not required": "gerekmez",
    "required approval": "gerekli",
}


def _plain(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^\s*>\s*", "", text)
    text = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", text)
    text = text.replace("**", "").replace("__", "")
    return text.strip(" \t`")


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", _plain(value).casefold()).strip()


def _canonical_value(field: str, value: str) -> str:
    cleaned = _plain(value)
    alias = _VALUE_ALIASES.get(cleaned.casefold())
    if alias:
        return alias
    return cleaned


def normalize_planning_markdown(text: str) -> str:
    """
    Normalize common LLM Markdown variants to the strict planning grammar.

    Examples accepted:
      ### TASK-001: Add tests
      **TASK-001 — Add tests**
      - **Seviye:** zorunlu
      * Assigned Agent: qa
    """
    normalized_lines: list[str] = []

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        stripped = raw_line.strip()

        if not stripped:
            normalized_lines.append("")
            continue

        task_match = _TASK_HEADER.match(stripped)
        if task_match:
            task_id = task_match.group(1).upper()
            title = _plain(task_match.group(2)).strip("* ")
            normalized_lines.append(f"### {task_id} — {title}")
            continue

        section_candidate = _plain(stripped)
        section_candidate = re.sub(
            r"^#{1,6}\s*",
            "",
            section_candidate,
        ).strip(" :*")
        canonical_section = _SECTION_ALIASES.get(_key(section_candidate))
        if canonical_section:
            normalized_lines.append(canonical_section)
            continue

        field_candidate = _plain(stripped)
        field_match = re.match(
            r"^([^:]{2,60})\s*:\s*(.*)$",
            field_candidate,
        )
        if field_match:
            canonical = _FIELD_ALIASES.get(_key(field_match.group(1)))
            if canonical:
                value = _canonical_value(
                    canonical,
                    field_match.group(2),
                )
                normalized_lines.append(
                    f"{canonical}: {value}".rstrip()
                )
                continue

        criteria_key = _key(field_candidate.rstrip(":"))
        if criteria_key in {
            "kabul kriterleri",
            "kabul kriteri",
            "acceptance criteria",
            "acceptance criterion",
        }:
            normalized_lines.append("Kabul Kriterleri:")
            continue

        normalized_lines.append(raw_line.rstrip())

    return "\n".join(normalized_lines).strip()
