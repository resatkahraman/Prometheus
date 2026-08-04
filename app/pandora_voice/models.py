from __future__ import annotations

import enum
from dataclasses import dataclass


class PandoraVoiceMode(str, enum.Enum):
    NORMAL = "normal"
    WEATHER = "weather"
    NEWS = "news"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

    @classmethod
    def parse(cls, value: str | "PandoraVoiceMode") -> "PandoraVoiceMode":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in cls)
            raise ValueError(f"Unsupported Pandora voice mode: {value!r}. Allowed: {allowed}") from exc


@dataclass(frozen=True)
class PandoraAudioResult:
    audio_bytes: bytes
    sample_rate: int
    duration_seconds: float
    mode: PandoraVoiceMode
    voice_profile_hash: str
    generation_time_seconds: float
    from_cache: bool = False
    chunk_index: int = 0
    total_chunks: int = 1
