from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioMetrics:
    duration_seconds: float
    sample_rate: int
    channels: int
    bit_depth: int
    peak_amplitude: float
    rms_amplitude: float
    silence_ratio: float
    clipping_ratio: float
    dc_offset: float

    @property
    def selectable(self) -> bool:
        return (
            self.channels == 1
            and self.sample_rate >= 16000
            and self.duration_seconds > 0
            and self.peak_amplitude <= 1.0
            and self.clipping_ratio <= 0.001
            and abs(self.dc_offset) <= 0.05
            and self.rms_amplitude >= 0.005
            and self.silence_ratio <= 0.80
        )


def analyze_wav(wav_path: str | Path) -> AudioMetrics:
    with wave.open(str(wav_path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        width = wav_file.getsampwidth()
        rate = wav_file.getframerate()
        frames = wav_file.getnframes()
        raw = wav_file.readframes(frames)

    count = frames * channels
    if count <= 0 or rate <= 0:
        raise ValueError("WAV contains no audio frames")

    if width == 1:
        values = struct.unpack(f"<{count}B", raw)
        normalized = [(value - 128) / 128.0 for value in values]
    elif width == 2:
        values = struct.unpack(f"<{count}h", raw)
        normalized = [value / 32768.0 for value in values]
    elif width == 3:
        normalized = []
        for offset in range(0, len(raw), 3):
            value = int.from_bytes(raw[offset:offset + 3], "little", signed=True)
            normalized.append(value / 8388608.0)
    elif width == 4:
        values = struct.unpack(f"<{count}i", raw)
        normalized = [value / 2147483648.0 for value in values]
    else:
        raise ValueError(f"Unsupported PCM sample width: {width}")

    if not normalized or any(not math.isfinite(sample) for sample in normalized):
        raise ValueError("WAV contains invalid samples")

    absolute = [abs(sample) for sample in normalized]
    peak = max(absolute)
    rms = math.sqrt(sum(sample * sample for sample in normalized) / len(normalized))
    silence = sum(sample < 0.01 for sample in absolute) / len(absolute)
    clipping = sum(sample >= 0.999 for sample in absolute) / len(absolute)
    dc = sum(normalized) / len(normalized)

    return AudioMetrics(
        duration_seconds=round(frames / rate, 3),
        sample_rate=rate,
        channels=channels,
        bit_depth=width * 8,
        peak_amplitude=round(peak, 6),
        rms_amplitude=round(rms, 6),
        silence_ratio=round(silence, 6),
        clipping_ratio=round(clipping, 8),
        dc_offset=round(dc, 6),
    )
