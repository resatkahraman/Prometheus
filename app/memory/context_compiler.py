from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class ContextSegment:
    """One independently budgeted piece of model context.

    ``required`` means the segment may not be shortened or omitted before
    active mode can use the compilation. Shadow mode may still render a
    clipped candidate, but marks it as ineligible so token savings never hide
    a quality regression.
    """

    id: str
    layer: str
    text: str
    priority: int
    required: bool = False
    source_path: str | None = None
    source_sha256: str | None = None


@dataclass(frozen=True)
class ContextCompilation:
    text: str
    chars: int
    estimated_tokens: int
    baseline_chars: int
    baseline_estimated_tokens: int
    saved_chars: int
    selected_segment_ids: list[str]
    omitted_segment_ids: list[str]
    deduplicated_segment_ids: list[str]
    source_hashes: dict[str, str]
    missing_evidence: list[str]
    fallback_required: bool
    eligible: bool
    cache_key: str


class ContextCompiler:
    """Builds a deterministic, provenance-carrying context capsule.

    The compiler itself is deliberately model-free. It cannot invent a
    summary: it may only select, deduplicate or clip text that Prometheus already
    obtained from local source/evidence. This makes it suitable for shadow
    measurement before any active prompt behavior is changed.
    """

    revision = "context-compiler-v1"

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _render(segment: ContextSegment) -> str:
        label = segment.source_path or segment.id
        required = "!" if segment.required else ""
        digest = (
            f" @{segment.source_sha256[:12]}"
            if segment.source_sha256
            else ""
        )
        return (
            f"[{segment.layer}{required} {label}{digest}]\n"
            f"{segment.text.strip()}"
        )

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        marker = "\n... CONTEXT_COMPILER_REQUIRED_FALLBACK ...\n"
        if limit <= len(marker) + 2:
            return value[: max(0, limit)]
        available = limit - len(marker)
        head = max(1, int(available * 0.7))
        tail = max(1, available - head)
        return value[:head] + marker + value[-tail:]

    def compile(
        self,
        *,
        task_text: str,
        segments: list[ContextSegment],
        max_chars: int,
        baseline_chars: int | None = None,
        missing_evidence: list[str] | None = None,
    ) -> ContextCompilation:
        if max_chars < 200:
            raise ValueError("Context compiler budget must be at least 200 chars.")

        unique: dict[str, tuple[int, ContextSegment]] = {}
        deduplicated: list[str] = []
        for index, segment in enumerate(segments):
            if not segment.text.strip():
                continue
            content_hash = self._digest(segment.text.strip())
            previous = unique.get(content_hash)
            if previous is None:
                unique[content_hash] = (index, segment)
                continue
            deduplicated.append(segment.id)
            previous_index, previous_segment = previous
            if (
                segment.required and not previous_segment.required
            ) or segment.priority > previous_segment.priority:
                unique[content_hash] = (previous_index, segment)

        candidates = list(unique.values())
        candidates.sort(
            key=lambda item: (
                0 if item[1].required else 1,
                -item[1].priority,
                item[0],
                item[1].id,
            )
        )

        header = "ADAM_CTX_V1 | source-backed; ! requires full fallback"
        chunks = [header.rstrip()]
        used = len(chunks[0])
        selected: list[str] = []
        omitted: list[str] = []
        required_was_clipped = False

        for _index, segment in candidates:
            rendered = self._render(segment)
            separator_chars = 2
            available = max_chars - used - separator_chars
            if len(rendered) <= available:
                chunks.append(rendered)
                used += separator_chars + len(rendered)
                selected.append(segment.id)
                continue
            if not segment.required or available <= 0:
                omitted.append(segment.id)
                if segment.required:
                    required_was_clipped = True
                continue
            chunks.append(self._clip(rendered, available))
            used += separator_chars + len(chunks[-1])
            selected.append(segment.id)
            required_was_clipped = True

        text = "\n\n".join(chunks)
        evidence_gaps = list(
            dict.fromkeys(
                item.strip()
                for item in (missing_evidence or [])
                if item.strip()
            )
        )
        fallback_required = required_was_clipped or bool(evidence_gaps)
        source_hashes = {
            segment.source_path: segment.source_sha256
            for _index, segment in candidates
            if segment.source_path and segment.source_sha256
        }
        baseline = (
            max(0, int(baseline_chars))
            if baseline_chars is not None
            else sum(len(segment.text) for _index, segment in candidates)
        )
        cache_payload = {
            "revision": self.revision,
            "task": self._digest(task_text),
            "budget": max_chars,
            "segments": [
                {
                    "id": segment.id,
                    "layer": segment.layer,
                    "required": segment.required,
                    "text": self._digest(segment.text),
                    "source_path": segment.source_path,
                    "source_sha256": segment.source_sha256,
                }
                for _index, segment in candidates
            ],
            "missing_evidence": evidence_gaps,
        }
        cache_key = self._digest(
            json.dumps(
                cache_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return ContextCompilation(
            text=text,
            chars=len(text),
            estimated_tokens=math.ceil(len(text) / 4),
            baseline_chars=baseline,
            baseline_estimated_tokens=math.ceil(baseline / 4),
            saved_chars=max(0, baseline - len(text)),
            selected_segment_ids=selected,
            omitted_segment_ids=omitted,
            deduplicated_segment_ids=deduplicated,
            source_hashes=source_hashes,
            missing_evidence=evidence_gaps,
            fallback_required=fallback_required,
            eligible=not fallback_required,
            cache_key=cache_key,
        )
