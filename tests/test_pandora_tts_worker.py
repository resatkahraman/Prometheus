from __future__ import annotations

import io
import wave

import pytest

import tools.pandora_tts_worker as worker
from app.pandora_voice.models import PandoraAudioResult, PandoraVoiceMode


def _wav(frames: int = 160, sample_rate: int = 16000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def _result(index: int = 0, total: int = 1) -> PandoraAudioResult:
    return PandoraAudioResult(
        audio_bytes=_wav(),
        sample_rate=16000,
        duration_seconds=0.01,
        mode=PandoraVoiceMode.NORMAL,
        voice_profile_hash="a" * 64,
        generation_time_seconds=0.1,
        chunk_index=index,
        total_chunks=total,
    )


def test_combine_wav_preserves_format_and_adds_pause() -> None:
    audio, duration = worker._combine_wav([_result(0, 2), _result(1, 2)], pause_ms=100)
    with wave.open(io.BytesIO(audio), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 16000
        assert handle.getnframes() == 160 + 1600 + 160
    assert duration == pytest.approx(0.12)


def test_bearer_token_validation_does_not_require_aiohttp() -> None:
    assert worker._has_valid_bearer({}) is False
    assert worker._has_valid_bearer({"Authorization": "Bearer wrong"}) is False
    assert worker._has_valid_bearer(
        {"Authorization": f"Bearer {worker._TOKEN}"}
    ) is True


def test_create_app_reports_missing_isolated_dependency(monkeypatch) -> None:
    monkeypatch.setattr(worker, "web", None)
    with pytest.raises(RuntimeError, match="isolated Pandora TTS environment"):
        worker.create_app()


def test_worker_source_does_not_log_plaintext_token() -> None:
    source = (worker._PROJECT_ROOT / "tools" / "pandora_tts_worker.py").read_text(
        encoding="utf-8"
    )
    assert 'logger.info("Pandora TTS token' not in source
    assert '"token": _TOKEN' in source
    assert "access_log=None" in source
