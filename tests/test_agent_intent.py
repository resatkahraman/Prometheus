from app.agent.intent import suggest_deterministic_tool
from app.core.schemas import ChatMessage


def test_istanbul_datetime_is_resolved_deterministically():
    suggestion = suggest_deterministic_tool(
        [
            ChatMessage(
                role="user",
                content=(
                    "Europe/Istanbul saat diliminde şu an tarih ve saat nedir?"
                ),
            )
        ]
    )
    assert suggestion is not None
    assert suggestion.tool == "current_datetime"
    assert suggestion.arguments == {"timezone": "Europe/Istanbul"}


def test_text_stats_extracts_only_payload_after_colon():
    suggestion = suggest_deterministic_tool(
        [
            ChatMessage(
                role="user",
                content=(
                    "Şu metnin kelime ve karakter sayısını hesapla: "
                    "Adam farklı modelleri birleştirir."
                ),
            )
        ]
    )
    assert suggestion is not None
    assert suggestion.tool == "text_stats"
    assert suggestion.arguments["text"] == (
        "Adam farklı modelleri birleştirir."
    )
