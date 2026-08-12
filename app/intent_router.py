"""Typed, deterministic conversational-vs-agentic routing boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class IntentRoute(str, Enum):
    CONVERSATION = "conversation"
    INFORMATIONAL = "informational"
    AGENTIC_TASK = "agentic_task"
    AMBIGUOUS = "ambiguous"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class IntentDecision:
    route: IntentRoute
    reason: str
    authority: str = "none"


_AGENTIC = re.compile(r"\b(d[üu]zelt|ekle|sil|merge|birleştir|birles[tş]ir|g[öo]nder|yap|oluştur|olustur|çalıştır|calistir|testleri|bug[ıi]|feature|dosyay[ıi])\b", re.I)
_INFORMATIONAL = re.compile(r"\b(nedir|ne yapıyor|ne yapiyor|nasıl|nasil|neden|açıkla|acikla|hakkında|hakkinda|selam|merhaba|hello|hi)\b", re.I)
_HIGH_RISK = re.compile(r"\b(sil|merge|birleştir|birleştir|g[öo]nder|ödeme|odeme|satın|satin|şifre|sifre|parola|push|deploy|yayınla|yayinla)\b", re.I)


def classify_intent(text: str, *, model_proposal: object | None = None) -> IntentDecision:
    if not isinstance(text, str) or not text.strip():
        return IntentDecision(IntentRoute.AMBIGUOUS, "empty_or_invalid_input")
    value = text.strip()
    lowered = value.casefold()
    if re.match(r"^(selam|merhaba|hello|hi)\b", lowered):
        return IntentDecision(IntentRoute.CONVERSATION, "greeting")
    if _AGENTIC.search(value):
        authority = "approval_or_capability_required" if _HIGH_RISK.search(value) else "existing_mission_authority_required"
        return IntentDecision(IntentRoute.AGENTIC_TASK, "explicit_action_language", authority)
    if _INFORMATIONAL.search(value) or value.endswith("?"):
        return IntentDecision(IntentRoute.INFORMATIONAL, "question_or_conversation_language")
    # Model output is advisory only; malformed/unknown proposals cannot elevate a route.
    if model_proposal is not None:
        if not isinstance(model_proposal, dict) or model_proposal.get("intent") not in {item.value.upper() for item in IntentRoute}:
            return IntentDecision(IntentRoute.AMBIGUOUS, "untrusted_or_malformed_model_proposal")
    return IntentDecision(IntentRoute.CONVERSATION, "default_bounded_conversation")
