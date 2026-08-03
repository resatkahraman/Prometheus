import re

from app.core.schemas import ChatMessage, TaskType


CODE_PATTERNS = re.compile(
    r"\b("
    r"kod|code|python|javascript|typescript|java|kotlin|flutter|dart|"
    r"c\+\+|c#|sql|api|endpoint|bug|hata|debug|refactor|github|git|"
    r"docker|kubernetes|fastapi|react|angular|vue|verilog|compile|"
    r"stack trace|exception|terminal|powershell"
    r")\b",
    flags=re.IGNORECASE,
)

SUMMARY_PATTERNS = re.compile(
    r"\b("
    r"özetle|özet çıkar|summarize|summary|kısalt|ana fikir|"
    r"maddeleştir|not çıkar"
    r")\b",
    flags=re.IGNORECASE,
)

TRANSLATION_PATTERNS = re.compile(
    r"\b("
    r"çevir|tercüme|translate|translation|ingilizceye|türkçeye|"
    r"almancaya|fransızcaya"
    r")\b",
    flags=re.IGNORECASE,
)

REASONING_PATTERNS = re.compile(
    r"\b("
    r"analiz et|karşılaştır|neden|nasıl karar|strateji|mimari|"
    r"risk|avantaj|dezavantaj|kanıtla|ispatla|değerlendir|"
    r"en iyi yaklaşım|plan oluştur|çok adımlı|derinlemesine"
    r")\b",
    flags=re.IGNORECASE,
)


class TaskClassifier:
    @staticmethod
    def text(messages: list[ChatMessage]) -> str:
        return "\n".join(message.content for message in messages)

    def classify(self, messages: list[ChatMessage]) -> TaskType:
        text = self.text(messages)

        if CODE_PATTERNS.search(text):
            return "coding"
        if SUMMARY_PATTERNS.search(text):
            return "summarization"
        if TRANSLATION_PATTERNS.search(text):
            return "translation"
        if REASONING_PATTERNS.search(text):
            return "reasoning"
        return "general"
