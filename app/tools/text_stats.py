import re
from typing import Any

from app.tools.base import BaseTool, ToolError


class TextStatsTool(BaseTool):
    name = "text_stats"
    description = (
        "Bir metnin karakter, boşluksuz karakter, kelime ve satır sayısını "
        "deterministik olarak hesaplar."
    )
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "İstatistiği çıkarılacak metin."}},
        "required": ["text"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        text = arguments.get("text")
        if not isinstance(text, str):
            raise ToolError("'text' bir metin olmalıdır.")
        if len(text) > 50_000:
            raise ToolError("Metin araç sınırını aşıyor.")
        words = re.findall(r"\S+", text)
        return {
            "characters": len(text),
            "characters_without_whitespace": len(re.sub(r"\s", "", text)),
            "words": len(words),
            "lines": len(text.splitlines()) if text else 0,
        }
