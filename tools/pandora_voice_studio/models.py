from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CandidateManifest:
    candidate_id: str
    seed: int
    persona_hash: str
    model_revision: str
    reference_path: str
    reference_sha256: str
    reference_transcript: str
    clips: dict[str, str] = field(default_factory=dict)
    clip_sha256: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    favorite: bool = False
    rejected: bool = False


@dataclass
class PackManifest:
    pack_hash: str
    model_id: str
    model_revision: str
    persona_hash: str
    candidates: list[CandidateManifest] = field(default_factory=list)
    import_timestamp: str = ""
