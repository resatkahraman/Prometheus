from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_TOKEN = re.compile(r"[a-zA-Z0-9_.$/-]+")


@dataclass(frozen=True)
class AttentionCard:
    id: str
    claim: str
    source_path: str | None
    evidence_type: str
    state: str
    confidence: float


@dataclass(frozen=True)
class ContextCapsule:
    text: str
    selected_card_ids: list[str]
    omitted_cards: int
    chars: int


class AttentionBroker:
    """Selects the highest-value evidence under a deterministic char budget."""

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {
            token.casefold()
            for token in _TOKEN.findall(value)
            if len(token) > 1
        }

    def _score(
        self,
        card: AttentionCard,
        *,
        task_tokens: set[str],
        target_path: str | None,
    ) -> float:
        card_tokens = self._tokens(
            f"{card.claim} {card.source_path or ''}"
        )
        overlap = len(task_tokens & card_tokens)
        score = overlap * 8.0 + card.confidence * 10.0
        if card.state == "verified":
            score += 10.0
        if target_path and card.source_path == target_path:
            score += 40.0
        if card.evidence_type in {"test", "user_decision"}:
            score += 15.0
        return score

    def build_capsule(
        self,
        *,
        task_text: str,
        target_path: str | None,
        cards: Iterable[AttentionCard],
        max_chars: int,
    ) -> ContextCapsule:
        candidates = []
        task_tokens = self._tokens(
            f"{task_text} {target_path or ''}"
        )
        for card in cards:
            label = (
                "VERIFIED"
                if card.state == "verified"
                else "HYPOTHESIS"
            )
            line = (
                f"- [{label}] {card.claim} "
                f"(source={card.source_path or 'none'}, "
                f"evidence={card.evidence_type}, "
                f"confidence={card.confidence:.2f})"
            )
            score = self._score(
                card,
                task_tokens=task_tokens,
                target_path=target_path,
            )
            candidates.append((score / max(1, len(line)), score, line, card))

        candidates.sort(
            key=lambda item: (-item[0], -item[1], item[3].id)
        )
        header = (
            "EVIDENCE_CAPSULE_V1\n"
            "Verified facts may be trusted. Hypotheses are ideas only and "
            "must not be treated as project facts.\n"
        )
        selected_lines: list[str] = []
        selected_ids: list[str] = []
        used = len(header)
        for _density, _score, line, card in candidates:
            addition = len(line) + 1
            if used + addition > max_chars:
                continue
            selected_lines.append(line)
            selected_ids.append(card.id)
            used += addition
        text = header + "\n".join(selected_lines)
        return ContextCapsule(
            text=text,
            selected_card_ids=selected_ids,
            omitted_cards=max(0, len(candidates) - len(selected_ids)),
            chars=len(text),
        )
