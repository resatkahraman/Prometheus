from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

CONTEXT_BOUNDS_REVISION = "context-bounds-v1"
CONTEXT_BOUNDARY_MARKER = "\n...[CONTEXT_BOUNDARY_TRUNCATED]...\n"


@dataclass(frozen=True)
class ContextPart:
    id: str
    text: str
    priority: int
    required: bool = False


@dataclass(frozen=True)
class BoundedContext:
    text: str
    chars: int
    original_chars: int
    max_chars: int
    truncated: bool
    selected_part_ids: tuple[str, ...] = ()
    omitted_part_ids: tuple[str, ...] = ()
    clipped_part_ids: tuple[str, ...] = ()
    required_overflow: bool = False
    digest: str = ""


class ContextBounds:
    @staticmethod
    def digest(value: str) -> str:
        return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def bound_text(cls, value: str, *, max_chars: int, marker: str = CONTEXT_BOUNDARY_MARKER) -> BoundedContext:
        if max_chars < 1:
            raise ValueError("Context bound must be at least 1 character.")
        original = len(value)
        if original <= max_chars:
            output = value
            truncated = False
        elif max_chars <= len(marker):
            output = value[:max_chars]
            truncated = True
        else:
            available = max_chars - len(marker)
            head_chars = (available * 65 + 99) // 100
            tail_chars = available - head_chars
            output = value[:head_chars] + marker
            if tail_chars:
                output += value[-tail_chars:]
            output = output[:max_chars]
            truncated = True
        return BoundedContext(output, len(output), original, max_chars, truncated, digest=cls.digest(output))

    @classmethod
    def assemble(cls, parts: Iterable[ContextPart], *, max_chars: int, separator: str = "\n\n") -> BoundedContext:
        if max_chars < 1:
            raise ValueError("Context bound must be at least 1 character.")
        indexed = list(parts)
        seen: set[str] = set()
        for part in indexed:
            if (
                not part.id.strip()
                or any(not (char.isalnum() or char in "_-:.") for char in part.id)
                or part.id in seen
            ):
                raise ValueError("Context part identifiers must be unique and non-empty.")
            seen.add(part.id)
        nonempty = [(index, part) for index, part in enumerate(indexed) if part.text]
        ordered = sorted(nonempty, key=lambda item: (0 if item[1].required else 1, -item[1].priority, item[0]))
        original_chars = sum(len(part.text) for _, part in nonempty) + max(0, len(nonempty) - 1) * len(separator)
        selected: list[tuple[ContextPart, str]] = []
        omitted: list[str] = []
        clipped: list[str] = []
        required_overflow = False
        used = 0
        for position, (_, part) in enumerate(ordered):
            cost_prefix = len(separator) if selected else 0
            available = max_chars - used - cost_prefix
            if available <= 0:
                omitted.append(part.id)
                if part.required:
                    required_overflow = True
                continue
            if len(part.text) <= available:
                rendered = part.text
            else:
                rendered = cls.bound_text(part.text, max_chars=available).text
                clipped.append(part.id)
                if part.required:
                    required_overflow = True
            if selected:
                used += len(separator)
            selected.append((part, rendered))
            used += len(rendered)
            if len(rendered) < len(part.text):
                for _, later in ordered[position + 1:]:
                    if later.id not in omitted and later.id != part.id:
                        omitted.append(later.id)
                break
        text = separator.join(rendered for _, rendered in selected)[:max_chars]
        return BoundedContext(text, len(text), original_chars, max_chars, len(text) < original_chars, tuple(p.id for p, _ in selected), tuple(omitted), tuple(clipped), required_overflow, cls.digest(text))
