from __future__ import annotations

import re
from urllib.parse import urlparse


_TECH_TERMS = {
    "FastAPI": "Fast A P İ",
    "pytest": "pay test",
    "API": "A P İ",
    "GPU": "G P U",
    "VRAM": "V Ram",
    "CPU": "C P U",
    "RAM": "Ram",
    "CUDA": "kuda",
    "JSON": "ceyson",
    "HTML": "H T M L",
    "CSS": "C S S",
    "HTTPS": "H T T P S",
    "HTTP": "H T T P",
    "TTS": "T T S",
    "WAV": "vav",
    "ZIP": "zip",
    "GB": "gigabayt",
    "MB": "megabayt",
}

_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}
_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]

_SECRET_PATTERNS = [
    re.compile(r"\b(?:sk|pk|gh[oprs]|github_pat|glpat|xox[boaprs]|AKIA)[-_][A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    re.compile(r"\b(?:token|password|secret|api[_ -]?key)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{64,}\b", re.IGNORECASE),
]

_PATH_RE = re.compile(r"(?i)\b[A-Z]:[\\/](?:[^<>:\"|?*\r\n]+[\\/])*[^<>:\"|?*\r\n]*")
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_SHA_RE = re.compile(r"\b[0-9a-f]{8,40}\b", re.IGNORECASE)


def number_to_turkish(value: int) -> str:
    if value == 0:
        return "sıfır"
    if value < 0:
        return "eksi " + number_to_turkish(-value)
    if value > 999_999_999_999:
        return str(value)

    parts: list[str] = []
    for divisor, label in (
        (1_000_000_000, "milyar"),
        (1_000_000, "milyon"),
        (1_000, "bin"),
    ):
        count, value = divmod(value, divisor)
        if count:
            if count != 1:
                parts.append(number_to_turkish(count))
            parts.append(label)

    hundreds, value = divmod(value, 100)
    if hundreds:
        if hundreds != 1:
            parts.append(_ONES[hundreds])
        parts.append("yüz")
    tens, ones = divmod(value, 10)
    if tens:
        parts.append(_TENS[tens])
    if ones:
        parts.append(_ONES[ones])
    return " ".join(parts)


def _redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("gizli değer", text)
    return text


def _replace_url(match: re.Match[str]) -> str:
    raw = match.group(0).rstrip(".,;:")
    try:
        host = urlparse(raw).hostname
    except ValueError:
        host = None
    return host or "internet bağlantısı"


def _replace_path(match: re.Match[str]) -> str:
    value = match.group(0).rstrip(".,;:")
    name = re.split(r"[\\/]", value)[-1].strip()
    return name or "dosya yolu"


def _replace_sha(match: re.Match[str]) -> str:
    short = match.group(0)[:7].lower()
    return " ".join(short)


def _normalize_dates(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        day, month, year = map(int, match.groups())
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return match.group(0)
        return f"{number_to_turkish(day)} {_MONTHS[month]} {number_to_turkish(year)}"
    return re.sub(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", repl, text)


def _normalize_times(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        hour, minute = map(int, match.groups())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return match.group(0)
        if minute == 0:
            return number_to_turkish(hour)
        return f"{number_to_turkish(hour)} {number_to_turkish(minute)}"
    return re.sub(r"\b(\d{1,2})[:.](\d{2})\b", repl, text)


def _normalize_percentages(text: str) -> str:
    text = re.sub(
        r"%\s*(\d+)",
        lambda m: "yüzde " + number_to_turkish(int(m.group(1))),
        text,
    )
    return re.sub(
        r"\b(\d+)\s*%",
        lambda m: "yüzde " + number_to_turkish(int(m.group(1))),
        text,
    )


def _normalize_fractions(text: str) -> str:
    return re.sub(
        r"\b(\d+)/(\d+)\b",
        lambda m: f"{number_to_turkish(int(m.group(1)))} bölü {number_to_turkish(int(m.group(2)))}",
        text,
    )


def _normalize_branches(text: str) -> str:
    pattern = re.compile(r"\b(?:task|feature|fix|hotfix|release|bugfix)-[a-z0-9_-]+\b", re.IGNORECASE)
    return pattern.sub(lambda m: m.group(0).replace("-", " ").replace("_", " "), text)


def _normalize_tech_terms(text: str) -> str:
    for term, spoken in sorted(_TECH_TERMS.items(), key=lambda item: -len(item[0])):
        text = re.sub(rf"\b{re.escape(term)}\b", spoken, text, flags=re.IGNORECASE)
    return text


def _normalize_numbers(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            return number_to_turkish(int(raw))
        except ValueError:
            return raw
    return re.sub(r"\b\d{1,12}\b", repl, text)


def normalize_for_tts(text: str, *, max_chars: int = 4000) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    text = text[:max_chars]
    text = _redact_secrets(text)
    text = _URL_RE.sub(_replace_url, text)
    text = _PATH_RE.sub(_replace_path, text)
    text = _SHA_RE.sub(_replace_sha, text)
    text = _normalize_branches(text)
    text = _normalize_dates(text)
    text = _normalize_times(text)
    text = _normalize_percentages(text)
    text = _normalize_fractions(text)
    text = _normalize_tech_terms(text)
    text = _normalize_numbers(text)
    return re.sub(r"\s+", " ", text).strip()


def make_speak_text(full_text: str, *, max_speak_chars: int = 300) -> str:
    if len(full_text) <= max_speak_chars:
        return normalize_for_tts(full_text)
    sentences = re.split(r"(?<=[.!?])\s+", full_text)
    selected: list[str] = []
    used = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        extra = len(sentence) + (1 if selected else 0)
        if used + extra > max_speak_chars:
            break
        selected.append(sentence)
        used += extra
    if not selected:
        selected = [full_text[:max_speak_chars].rsplit(" ", 1)[0] or full_text[:max_speak_chars]]
    return normalize_for_tts(" ".join(selected))


def _hard_split(value: str, hard_max_chars: int) -> list[str]:
    output: list[str] = []
    remaining = value.strip()
    while len(remaining) > hard_max_chars:
        cut = remaining.rfind(" ", 0, hard_max_chars + 1)
        if cut < hard_max_chars // 2:
            cut = hard_max_chars
        output.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        output.append(remaining)
    return output


def chunk_text(
    text: str,
    *,
    target_chars: int = 180,
    hard_max_chars: int = 260,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if target_chars <= 0 or hard_max_chars < target_chars:
        raise ValueError("invalid chunk limits")

    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        for part in _hard_split(sentence, hard_max_chars):
            candidate = f"{current} {part}".strip() if current else part
            if current and len(candidate) > target_chars:
                chunks.append(current)
                current = part
            else:
                current = candidate
            if len(current) >= hard_max_chars:
                chunks.append(current)
                current = ""

    if current:
        chunks.append(current)
    assert all(0 < len(chunk) <= hard_max_chars for chunk in chunks)
    return chunks
