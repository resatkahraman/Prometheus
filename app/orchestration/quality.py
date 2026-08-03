import re
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityResult:
    accepted: bool
    reason: str


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _looks_like_code(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith(
        (
            "```",
            "<<<ADAM_",
            "@@",
            "//",
            "/*",
            "* ",
            "{",
            "}",
            "<",
            "</",
            "#",
        )
    ):
        return True
    if stripped.endswith(("{", "}", ";", "/>", ">", ",")):
        return True
    if re.match(
        r"^(?:const|let|var|def|class|function|interface|type|import|"
        r"export|return|if|else|for|while|try|catch|async|await)\b",
        stripped,
        flags=re.IGNORECASE,
    ):
        return True
    return (
        re.search(
            r"(?:=>|[{};]|</?[A-Za-z][^>]*>|^\s*[.#][\w-]+\s*\{)",
            stripped,
        )
        is not None
    )


def inspect_response(text: str) -> QualityResult:
    """
    Detect obvious generation loops without judging factual correctness.

    The guard is deliberately conservative. It rejects repeated paragraph or
    sentence loops such as the same two sentences being emitted many times.
    """
    if not isinstance(text, str) or not text.strip():
        return QualityResult(False, "Model boş cevap üretti.")

    normalized_text = _normalize(text)
    if len(normalized_text) < 8:
        return QualityResult(False, "Model cevabı anlamlı olamayacak kadar kısa.")

    paragraphs = [
        _normalize(part)
        for part in re.split(r"\n\s*\n+", text)
        if _normalize(part)
    ]

    if len(paragraphs) >= 4:
        paragraph_counts: dict[str, int] = {}
        for paragraph in paragraphs:
            if len(paragraph) < 30:
                continue
            paragraph_counts[paragraph] = paragraph_counts.get(paragraph, 0) + 1

        maximum = max(paragraph_counts.values(), default=0)
        if maximum >= 3:
            return QualityResult(
                False,
                "Aynı paragraf üç veya daha fazla kez tekrarlandı.",
            )

    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        normalized = _normalize(sentence)
        if len(normalized) < 20 or _looks_like_code(sentence):
            continue
        sentences.append(normalized)

    if len(sentences) >= 8:
        unique_ratio = len(set(sentences)) / len(sentences)
        if unique_ratio < 0.55:
            return QualityResult(
                False,
                "Cümle tekrar oranı aşırı yüksek.",
            )

        sentence_counts: dict[str, int] = {}
        for sentence in sentences:
            sentence_counts[sentence] = sentence_counts.get(sentence, 0) + 1

        if max(sentence_counts.values(), default=0) >= 4:
            return QualityResult(
                False,
                "Aynı cümle dört veya daha fazla kez tekrarlandı.",
            )

    prose_text = " ".join(
        line
        for line in text.splitlines()
        if not _looks_like_code(line)
    )
    words = re.findall(
        r"\b[\wçğıöşüÇĞİÖŞÜ'-]+\b",
        _normalize(prose_text),
    )
    if len(words) >= 120:
        windows = [
            " ".join(words[index : index + 12])
            for index in range(0, len(words) - 11)
        ]
        counts: dict[str, int] = {}
        for window in windows:
            counts[window] = counts.get(window, 0) + 1

        if max(counts.values(), default=0) >= 4:
            return QualityResult(
                False,
                "Uzun bir kelime dizisi tekrar döngüsüne girdi.",
            )

    return QualityResult(True, "Cevap temel kalite kontrolünü geçti.")
