from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.pandora_voice.models import PandoraAudioResult


@runtime_checkable
class PandoraVoiceEngine(Protocol):
    @property
    def voice_profile_hash(self) -> str: ...

    @property
    def sample_rate(self) -> int: ...

    def synthesize(self, text: str, *, mode: str = "normal") -> PandoraAudioResult: ...

    def is_loaded(self) -> bool: ...

    def unload(self) -> None: ...

    def load(self) -> None: ...
