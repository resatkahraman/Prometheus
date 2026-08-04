from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _local_app_data() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else Path.home() / ".local" / "share"


@dataclass(frozen=True)
class PandoraVoiceConfig:
    engine: str = "chatterbox_multilingual_v3"
    model_id: str = "ResembleAI/chatterbox"
    model_revision: str = "e2d6902dd4c1301892935d0a0277325551e8060e"
    package_version: str = "0.1.7"
    language: str = "tr"

    model_cache_dir: Path = field(
        default_factory=lambda: _local_app_data() / "Prometheus" / "models" / "pandora" / "chatterbox-v3"
    )
    voice_asset_root: Path = field(
        default_factory=lambda: _local_app_data() / "Prometheus" / "pandora_voice"
    )
    audio_cache_dir: Path = field(
        default_factory=lambda: _local_app_data() / "Prometheus" / "cache" / "pandora_tts"
    )
    runtime_dir: Path = field(
        default_factory=lambda: _local_app_data() / "Prometheus" / "runtime"
    )

    # The dGPU is a 4096 MiB RTX 3050 Ti. Requiring 3750 MiB free would often
    # reject a healthy system because the driver may reserve several hundred MiB.
    min_free_vram_mib: int = 3200
    max_process_reserved_vram_mib: int = 3800

    max_concurrent_synthesis: int = 1
    max_queued_requests: int = 3
    request_timeout_seconds: float = 120.0
    idle_unload_seconds: float = 300.0

    chunk_target_chars: int = 180
    chunk_hard_max_chars: int = 260
    max_input_chars: int = 4000

    cache_max_bytes: int = 512 * 1024 * 1024
    cache_max_age_days: int = 7

    worker_host: str = "127.0.0.1"
    worker_port: int = 9723
    allow_model_download: bool = False

    @property
    def master_reference_dir(self) -> Path:
        return self.voice_asset_root / "master"

    @property
    def master_reference_wav(self) -> Path:
        return self.master_reference_dir / "pandora_reference.wav"

    @property
    def master_reference_text(self) -> Path:
        return self.master_reference_dir / "pandora_reference.txt"

    @property
    def master_voice_profile(self) -> Path:
        return self.master_reference_dir / "pandora_voice_profile.json"

    @property
    def worker_state_file(self) -> Path:
        return self.runtime_dir / "pandora_tts_worker.json"

    def validate(self) -> None:
        if self.engine != "chatterbox_multilingual_v3":
            raise ValueError(f"Unsupported engine: {self.engine}")
        if self.language != "tr":
            raise ValueError("Pandora production language must be 'tr'")
        if not _HEX40.fullmatch(self.model_revision):
            raise ValueError("production model revision must be an immutable 40-character commit SHA")
        if self.worker_host not in {"127.0.0.1", "::1"}:
            raise ValueError("Pandora worker must bind to loopback")
        if self.max_concurrent_synthesis != 1:
            raise ValueError("RTX 3050 Ti runtime supports exactly one active synthesis")
        if not (1 <= self.max_queued_requests <= 8):
            raise ValueError("max_queued_requests must be between 1 and 8")
        if not (1 <= self.request_timeout_seconds <= 600):
            raise ValueError("request_timeout_seconds must be between 1 and 600")
        if not (64 <= self.chunk_target_chars <= self.chunk_hard_max_chars <= 400):
            raise ValueError("invalid chunk limits")
        if self.max_input_chars < self.chunk_hard_max_chars:
            raise ValueError("max_input_chars must be >= chunk_hard_max_chars")

    @classmethod
    def from_models_json(cls, path: str | Path) -> "PandoraVoiceConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        prod = data.get("production_runtime")
        if not isinstance(prod, dict):
            raise ValueError("production_runtime object is required")
        cfg = cls(
            engine=str(prod.get("engine", "chatterbox_multilingual_v3")),
            model_id=str(prod.get("model_id", "ResembleAI/chatterbox")),
            model_revision=str(prod.get("revision", "")),
            package_version=str(prod.get("package_version", "0.1.7")),
            language=str(prod.get("language", "tr")),
        )
        cfg.validate()
        return cfg
