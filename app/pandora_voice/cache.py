from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

from app.pandora_voice.config import PandoraVoiceConfig
from app.pandora_voice.models import PandoraAudioResult, PandoraVoiceMode


_SENSITIVE = [
    re.compile(r"\b(?:onay|approval|confirm|parola|şifre|password|secret|token|api[_ -]?key)\b", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|gh[oprs]|github_pat|glpat|xox[boaprs])[-_][A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b[A-Z]:[\\/][^\r\n]+"),
]


def is_cacheable_text(text: str) -> bool:
    return bool(text.strip()) and not any(pattern.search(text) for pattern in _SENSITIVE)


class PandoraAudioCache:
    def __init__(self, config: PandoraVoiceConfig) -> None:
        self.config = config
        self.cache_dir = config.audio_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, text: str, mode: str, profile_hash: str) -> str:
        payload = json.dumps(
            {
                "text": text,
                "mode": mode,
                "voice_profile_hash": profile_hash,
                "model_revision": self.config.model_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.cache_dir / f"{key}.wav", self.cache_dir / f"{key}.json"

    def get(self, text: str, mode: str, profile_hash: str) -> PandoraAudioResult | None:
        if not is_cacheable_text(text):
            return None
        wav_path, meta_path = self._paths(self._key(text, mode, profile_hash))
        if not wav_path.is_file() or not meta_path.is_file():
            return None
        max_age = self.config.cache_max_age_days * 86400
        if time.time() - min(wav_path.stat().st_mtime, meta_path.stat().st_mtime) > max_age:
            self._delete_pair(wav_path, meta_path)
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            audio = wav_path.read_bytes()
            if hashlib.sha256(audio).hexdigest() != meta["audio_sha256"]:
                raise ValueError("cache audio hash mismatch")
            os.utime(wav_path, None)
            os.utime(meta_path, None)
            return PandoraAudioResult(
                audio_bytes=audio,
                sample_rate=int(meta["sample_rate"]),
                duration_seconds=float(meta["duration_seconds"]),
                mode=PandoraVoiceMode.parse(meta["mode"]),
                voice_profile_hash=str(meta["voice_profile_hash"]),
                generation_time_seconds=0.0,
                from_cache=True,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._delete_pair(wav_path, meta_path)
            return None

    def put(self, text: str, result: PandoraAudioResult) -> None:
        if not is_cacheable_text(text):
            return
        key = self._key(text, result.mode.value, result.voice_profile_hash)
        wav_path, meta_path = self._paths(key)
        meta = {
            "sample_rate": result.sample_rate,
            "duration_seconds": result.duration_seconds,
            "mode": result.mode.value,
            "voice_profile_hash": result.voice_profile_hash,
            "audio_sha256": hashlib.sha256(result.audio_bytes).hexdigest(),
        }
        self._atomic_write(wav_path, result.audio_bytes)
        self._atomic_write(meta_path, json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        self._enforce_limits()

    def _atomic_write(self, target: Path, payload: bytes) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", dir=self.cache_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    @staticmethod
    def _delete_pair(wav_path: Path, meta_path: Path) -> None:
        wav_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    def _enforce_limits(self) -> None:
        pairs: list[tuple[float, int, Path, Path]] = []
        total = 0
        for wav in self.cache_dir.glob("*.wav"):
            meta = wav.with_suffix(".json")
            if not meta.exists():
                wav.unlink(missing_ok=True)
                continue
            size = wav.stat().st_size + meta.stat().st_size
            age_key = min(wav.stat().st_mtime, meta.stat().st_mtime)
            total += size
            pairs.append((age_key, size, wav, meta))
        if total <= self.config.cache_max_bytes:
            return
        for _, size, wav, meta in sorted(pairs):
            self._delete_pair(wav, meta)
            total -= size
            if total <= int(self.config.cache_max_bytes * 0.8):
                break

    def clear(self) -> int:
        count = 0
        for path in list(self.cache_dir.glob("*.wav")) + list(self.cache_dir.glob("*.json")):
            path.unlink(missing_ok=True)
            count += 1
        return count
