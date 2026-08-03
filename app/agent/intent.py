import re
from dataclasses import dataclass
from typing import Any

from app.core.schemas import ChatMessage


@dataclass(frozen=True)
class ToolSuggestion:
    tool: str
    arguments: dict[str, Any]
    reason: str


IANA = re.compile(r"\b([A-Za-z_]+/[A-Za-z0-9_+\-]+)\b")
TIME = re.compile(
    r"\b("
    r"şu an|simdi|şimdi|bugün|tarih|saat|"
    r"current time|current date|what time|what date"
    r")\b",
    re.IGNORECASE,
)
TEXT = re.compile(
    r"\b("
    r"kelime say|karakter say|harf say|satır say|"
    r"word count|character count|text stats"
    r")",
    re.IGNORECASE,
)

TERMINAL = [
    (
        re.compile(
            r"(python.{0,30}(sözdizimi|syntax|compile|derle)|"
            r"(sözdizimi|syntax).{0,30}python)",
            re.IGNORECASE,
        ),
        "python_compile",
        "Açık Python sözdizimi isteği deterministik eşlendi.",
    ),
    (
        re.compile(
            r"(flutter\s+analy[sz]|flutter.{0,20}(analiz|lint))",
            re.IGNORECASE,
        ),
        "flutter_analyze",
        "Açık Flutter analiz isteği deterministik eşlendi.",
    ),
    (
        re.compile(
            r"(flutter\s+test|flutter.{0,20}test)",
            re.IGNORECASE,
        ),
        "flutter_test",
        "Açık Flutter test isteği deterministik eşlendi.",
    ),
    (
        re.compile(
            r"(pytest|python.{0,20}test(ler)?(i)?\s*(çalıştır|run))",
            re.IGNORECASE,
        ),
        "pytest",
        "Açık Python test isteği deterministik eşlendi.",
    ),
    (
        re.compile(
            r"(npm\s+(run\s+)?build|node.{0,20}build)",
            re.IGNORECASE,
        ),
        "npm_build",
        "Açık npm build isteği deterministik eşlendi.",
    ),
    (
        re.compile(
            r"(npm\s+test|node.{0,20}test(ler)?(i)?\s*(çalıştır|run))",
            re.IGNORECASE,
        ),
        "npm_test",
        "Açık npm test isteği deterministik eşlendi.",
    ),
    (
        re.compile(
            r"(gradle.{0,20}test|gradlew.{0,20}test)",
            re.IGNORECASE,
        ),
        "gradle_test",
        "Açık Gradle test isteği deterministik eşlendi.",
    ),
]

MATH_OPERATIONS = [
    (
        re.compile(r"\b(türev|derivative|differentiate)\w*", re.IGNORECASE),
        "differentiate",
        "Açık türev isteği symbolic_math aracına eşlendi.",
    ),
    (
        re.compile(r"\b(integral|integrate)\w*", re.IGNORECASE),
        "integrate",
        "Açık integral isteği symbolic_math aracına eşlendi.",
    ),
    (
        re.compile(
            r"\b(denklem|equation).{0,40}\b(çöz|solve)|"
            r"\b(çöz|solve).{0,40}\b(denklem|equation)",
            re.IGNORECASE,
        ),
        "solve",
        "Açık denklem çözme isteği symbolic_math aracına eşlendi.",
    ),
    (
        re.compile(r"\b(sadeleştir|simplify)\w*", re.IGNORECASE),
        "simplify",
        "Açık sadeleştirme isteği symbolic_math aracına eşlendi.",
    ),
]


def last_user_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def timezone(text: str) -> str | None:
    match = IANA.search(text)
    if match:
        return match.group(1)

    lowered = text.casefold()
    if any(
        item in lowered
        for item in ("istanbul", "türkiye", "turkiye", "turkey")
    ):
        return "Europe/Istanbul"

    if " utc" in f" {lowered}" or "gmt" in lowered:
        return "UTC"

    return None


def payload(text: str) -> str | None:
    if ":" in text:
        value = text.split(":", 1)[1].strip()
        if value:
            return value

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[1:]).strip() if len(lines) > 1 else None


def _extract_variable(text: str, expression: str) -> str | None:
    match = re.search(
        r"\b([A-Za-z_]\w*)\s*['’]?(?:e|a|ye|ya)\s+göre\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)

    identifiers = re.findall(r"\b[A-Za-z_]\w*\b", expression)
    ignored = {
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "sqrt",
        "log",
        "exp",
        "abs",
        "pi",
        "e",
    }
    symbols = [
        item
        for item in identifiers
        if item.casefold() not in ignored
    ]
    unique = list(dict.fromkeys(symbols))
    return unique[0] if len(unique) == 1 else None


def _equation_to_zero(expression: str) -> str:
    if "=" not in expression:
        return expression

    left, right = expression.split("=", 1)
    if not left.strip() or not right.strip():
        return expression

    return f"({left.strip()})-({right.strip()})"


def _extract_expression(text: str, operation: str) -> str | None:
    code_match = re.search(r"`([^`\n]+)`", text)
    if code_match:
        candidate = code_match.group(1).strip()
    else:
        markers = [
            r"\s+ifadesinin\b",
            r"\s+ifadesini\b",
            r"\s+ifadesi\b",
            r"\s+denklemini\b",
            r"\s+denklemi\b",
        ]
        candidate = ""
        for marker in markers:
            match = re.search(marker, text, flags=re.IGNORECASE)
            if match:
                candidate = text[: match.start()].strip()
                break

        if not candidate and ":" in text:
            candidate = text.split(":", 1)[1].strip()

    candidate = candidate.strip(" \t\n.,;:")
    candidate = re.sub(
        r"^(şu|bu)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )

    if not candidate:
        return None

    if len(candidate) > 1_000:
        return None

    if not re.fullmatch(r"[A-Za-z0-9_+\-*/().=\s]+", candidate):
        return None

    if not re.search(r"[+\-*/=()]|\*\*", candidate):
        return None

    if operation == "solve":
        return _equation_to_zero(candidate)

    return candidate


def _math_suggestion(text: str) -> ToolSuggestion | None:
    for pattern, operation, reason in MATH_OPERATIONS:
        if not pattern.search(text):
            continue

        expression = _extract_expression(text, operation)
        if not expression:
            return None

        arguments: dict[str, Any] = {
            "operation": operation,
            "expression": expression,
        }

        if operation in {"differentiate", "integrate", "solve"}:
            variable = _extract_variable(text, expression)
            if not variable:
                return None
            arguments["variable"] = variable

        return ToolSuggestion(
            tool="symbolic_math",
            arguments=arguments,
            reason=reason,
        )

    return None


def suggest_deterministic_tool(
    messages: list[ChatMessage],
    *,
    agent_id: str | None = None,
) -> ToolSuggestion | None:
    text = last_user_text(messages)
    if not text:
        return None

    for pattern, preset, reason in TERMINAL:
        if pattern.search(text):
            return ToolSuggestion(
                "safe_terminal",
                {"preset": preset, "extra_args": []},
                reason,
            )

    math = _math_suggestion(text)
    if math is not None:
        return math

    if TIME.search(text):
        zone = timezone(text)
        if zone:
            return ToolSuggestion(
                "current_datetime",
                {"timezone": zone},
                "Saat dilimi deterministik korundu.",
            )

    if TEXT.search(text):
        value = payload(text)
        if value:
            return ToolSuggestion(
                "text_stats",
                {"text": value},
                "Sayılacak metin deterministik ayrıştırıldı.",
            )

    return None
