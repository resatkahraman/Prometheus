from __future__ import annotations

import asyncio
import io
import math
import time
import wave
from dataclasses import replace
from pathlib import Path

import pytest

from app.pandora_voice.cache import PandoraAudioCache, is_cacheable_text
from app.pandora_voice.config import PandoraVoiceConfig
from app.pandora_voice.errors import PandoraSynthesisTimeoutError
from app.pandora_voice.models import PandoraAudioResult, PandoraVoiceMode
from app.pandora_voice.service import PandoraVoiceService


def _wav(seconds: float = 0.05, sample_rate: int = 16000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = b"".join(
            int(math.sin(i * 0.1) * 5000).to_bytes(2, "little", signed=True)
            for i in range(int(seconds * sample_rate))
        )
        handle.writeframes(frames)
    return output.getvalue()


class FakeEngine:
    def __init__(self, delay: float = 0.0) -> None:
        self.loaded = False
        self.delay = delay
        self.calls = 0
        self._hash = "a" * 64

    @property
    def voice_profile_hash(self) -> str:
        return self._hash

    @property
    def sample_rate(self) -> int:
        return 16000

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def is_loaded(self) -> bool:
        return self.loaded

    def synthesize(self, text: str, *, mode: str = "normal") -> PandoraAudioResult:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return PandoraAudioResult(
            audio_bytes=_wav(),
            sample_rate=16000,
            duration_seconds=0.05,
            mode=PandoraVoiceMode.parse(mode),
            voice_profile_hash=self._hash,
            generation_time_seconds=self.delay,
        )


def _config(tmp_path: Path, **changes) -> PandoraVoiceConfig:
    base = PandoraVoiceConfig(
        model_cache_dir=tmp_path / "models",
        voice_asset_root=tmp_path / "voice",
        audio_cache_dir=tmp_path / "cache",
        runtime_dir=tmp_path / "runtime",
        chunk_target_chars=80,
        chunk_hard_max_chars=120,
    )
    return replace(base, **changes)


@pytest.mark.asyncio
async def test_service_chunks_and_reuses_cache(tmp_path: Path) -> None:
    engine = FakeEngine()
    service = PandoraVoiceService(_config(tmp_path), engine)
    text = " ".join(["Pandora güvenli biçimde konuşur."] * 20)
    first = await service.synthesize(text)
    first_calls = engine.calls
    second = await service.synthesize(text)
    assert len(first) > 1
    assert engine.calls == first_calls
    assert all(item.from_cache for item in second)
    await service.close()


@pytest.mark.asyncio
async def test_timeout_poison_prevents_second_cuda_job(tmp_path: Path) -> None:
    engine = FakeEngine(delay=1.2)
    service = PandoraVoiceService(_config(tmp_path, request_timeout_seconds=1.0), engine)
    with pytest.raises(PandoraSynthesisTimeoutError):
        await service.synthesize("Merhaba Pandora", allow_cache=False)
    assert service.poisoned_reason
    with pytest.raises(PandoraSynthesisTimeoutError):
        await service.synthesize("İkinci istek", allow_cache=False)
    await service.close()


def test_sensitive_text_is_not_cached(tmp_path: Path) -> None:
    assert is_cacheable_text("Bugün hava güzel")
    assert not is_cacheable_text("Onay kodu ve token=abcdefghijklmnop")
    assert not is_cacheable_text(r"C:\Users\Example\private.txt")
