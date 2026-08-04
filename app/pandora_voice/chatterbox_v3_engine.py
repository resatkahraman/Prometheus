from __future__ import annotations

import gc
import hashlib
import io
import json
import logging
import math
import time
import wave
from pathlib import Path

from app.pandora_voice.config import PandoraVoiceConfig
from app.pandora_voice.errors import (
    PandoraGPUBusyError,
    PandoraMemoryError,
    PandoraModelNotLoadedError,
    PandoraReferenceIntegrityError,
    PandoraReferenceNotFoundError,
)
from app.pandora_voice.models import PandoraAudioResult, PandoraVoiceMode

logger = logging.getLogger(__name__)

_REQUIRED_MODEL_FILES = [
    "ve.pt",
    "t3_mtl23ls_v3.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
    "Cangjie5_TC.json",
]

_MODE_SETTINGS = {
    PandoraVoiceMode.NORMAL: {"exaggeration": 0.50, "cfg_weight": 0.50, "temperature": 0.80},
    PandoraVoiceMode.WEATHER: {"exaggeration": 0.55, "cfg_weight": 0.45, "temperature": 0.78},
    PandoraVoiceMode.NEWS: {"exaggeration": 0.42, "cfg_weight": 0.55, "temperature": 0.72},
    PandoraVoiceMode.SUCCESS: {"exaggeration": 0.55, "cfg_weight": 0.45, "temperature": 0.75},
    PandoraVoiceMode.WARNING: {"exaggeration": 0.30, "cfg_weight": 0.62, "temperature": 0.68},
    PandoraVoiceMode.ERROR: {"exaggeration": 0.28, "cfg_weight": 0.65, "temperature": 0.65},
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ChatterboxV3Engine:
    """Pinned Chatterbox Multilingual V3 runtime.

    The public Chatterbox `from_pretrained` helper downloads from `main`.
    To keep Pandora reproducible, this engine resolves an exact HF snapshot
    revision first and loads it through `from_local`.
    """

    def __init__(self, config: PandoraVoiceConfig) -> None:
        config.validate()
        self.config = config
        self._model = None
        self._sample_rate = 0
        self._voice_profile_hash = ""
        self._reference_wav_path: Path | None = None
        self._snapshot_path: Path | None = None

    @property
    def voice_profile_hash(self) -> str:
        return self._voice_profile_hash

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _load_profile(self) -> None:
        ref = self.config.master_reference_wav
        profile_path = self.config.master_voice_profile
        if not ref.is_file():
            raise PandoraReferenceNotFoundError(f"Master reference not found: {ref}")
        if not profile_path.is_file():
            raise PandoraReferenceNotFoundError(f"Voice profile not found: {profile_path}")

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        expected = str(profile.get("reference_sha256", "")).lower()
        actual = _sha256_file(ref)
        if not expected or expected != actual:
            raise PandoraReferenceIntegrityError(
                f"Pandora reference SHA mismatch: expected {expected or '<missing>'}, got {actual}"
            )
        if profile.get("approved_by_user") is not True:
            raise PandoraReferenceIntegrityError("Pandora voice profile is not explicitly approved")
        if str(profile.get("runtime_model", "")) != self.config.model_id:
            raise PandoraReferenceIntegrityError("Voice profile runtime model differs from configuration")
        if str(profile.get("runtime_revision", "")).lower() != self.config.model_revision:
            raise PandoraReferenceIntegrityError("Voice profile runtime revision differs from configuration")
        if str(profile.get("language", "")) != self.config.language:
            raise PandoraReferenceIntegrityError("Voice profile language differs from configuration")
        transcript_path = self.config.master_reference_text
        if not transcript_path.is_file() or not transcript_path.read_text(encoding="utf-8").strip():
            raise PandoraReferenceIntegrityError("Exact Pandora reference transcript is missing")
        self._reference_wav_path = ref
        self._voice_profile_hash = actual

    def _resolve_snapshot(self) -> Path:
        from huggingface_hub import snapshot_download

        path = snapshot_download(
            repo_id=self.config.model_id,
            repo_type="model",
            revision=self.config.model_revision,
            cache_dir=str(self.config.model_cache_dir),
            allow_patterns=_REQUIRED_MODEL_FILES,
            local_files_only=not self.config.allow_model_download,
        )
        snapshot = Path(path)
        missing = [name for name in _REQUIRED_MODEL_FILES if not (snapshot / name).exists()]
        if missing:
            raise FileNotFoundError(f"Incomplete Chatterbox V3 snapshot; missing: {', '.join(missing)}")
        return snapshot

    @staticmethod
    def _cuda_memory_mib(torch_module) -> tuple[int, int]:
        free_bytes, total_bytes = torch_module.cuda.mem_get_info()
        return int(free_bytes / 1024**2), int(total_bytes / 1024**2)

    def load(self) -> None:
        if self.is_loaded():
            return

        self._load_profile()

        import torch
        if not torch.cuda.is_available():
            raise PandoraGPUBusyError(0, self.config.min_free_vram_mib)

        free_mib, _ = self._cuda_memory_mib(torch)
        if free_mib < self.config.min_free_vram_mib:
            raise PandoraGPUBusyError(free_mib, self.config.min_free_vram_mib)

        torch.cuda.reset_peak_memory_stats()
        self._snapshot_path = self._resolve_snapshot()

        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        logger.info("Loading pinned Chatterbox Multilingual V3 snapshot.")
        try:
            self._model = ChatterboxMultilingualTTS.from_local(
                self._snapshot_path,
                device="cuda",
                t3_model="v3",
            )
            self._model.prepare_conditionals(str(self._reference_wav_path), exaggeration=0.5)
            self._sample_rate = int(self._model.sr)
            reserved = int(torch.cuda.max_memory_reserved() / 1024**2)
            if reserved > self.config.max_process_reserved_vram_mib:
                self.unload()
                raise PandoraMemoryError(reserved, self.config.max_process_reserved_vram_mib)
        except torch.cuda.OutOfMemoryError as exc:
            reserved = int(torch.cuda.max_memory_reserved() / 1024**2)
            self.unload()
            raise PandoraMemoryError(reserved, self.config.max_process_reserved_vram_mib) from exc

    def unload(self) -> None:
        self._model = None
        self._sample_rate = 0
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def is_loaded(self) -> bool:
        return self._model is not None

    def synthesize(self, text: str, *, mode: str = "normal") -> PandoraAudioResult:
        if self._model is None:
            raise PandoraModelNotLoadedError("Chatterbox Multilingual V3 is not loaded")
        if not text.strip():
            raise ValueError("text must not be empty")

        import numpy as np
        import torch

        voice_mode = PandoraVoiceMode.parse(mode)
        settings = _MODE_SETTINGS[voice_mode]
        started = time.perf_counter()
        try:
            with torch.inference_mode():
                wav_tensor = self._model.generate(
                    text,
                    language_id=self.config.language,
                    audio_prompt_path=None,
                    **settings,
                )
        except torch.cuda.OutOfMemoryError as exc:
            reserved = int(torch.cuda.max_memory_reserved() / 1024**2)
            raise PandoraMemoryError(reserved, self.config.max_process_reserved_vram_mib) from exc

        generation_seconds = time.perf_counter() - started
        audio = wav_tensor.detach().float().cpu().numpy() if isinstance(wav_tensor, torch.Tensor) else np.asarray(wav_tensor)
        audio = np.asarray(audio).squeeze()
        if audio.ndim != 1 or audio.size == 0:
            raise ValueError(f"Invalid audio shape from Chatterbox: {audio.shape}")
        audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)
        audio = np.clip(audio, -1.0, 1.0)
        pcm = np.round(audio * 32767.0).astype("<i2")

        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(pcm.tobytes())

        duration = float(pcm.size / self._sample_rate)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Chatterbox generated empty audio")

        return PandoraAudioResult(
            audio_bytes=output.getvalue(),
            sample_rate=self._sample_rate,
            duration_seconds=duration,
            mode=voice_mode,
            voice_profile_hash=self._voice_profile_hash,
            generation_time_seconds=generation_seconds,
        )
