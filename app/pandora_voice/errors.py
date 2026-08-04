from __future__ import annotations


class PandoraVoiceError(Exception):
    """Base error for Pandora Voice."""


class PandoraConfigurationError(PandoraVoiceError):
    pass


class PandoraGPUBusyError(PandoraVoiceError):
    def __init__(self, free_vram_mib: int, required_mib: int):
        self.free_vram_mib = free_vram_mib
        self.required_mib = required_mib
        super().__init__(f"GPU_BUSY: {free_vram_mib} MiB free; {required_mib} MiB required")


class PandoraMemoryError(PandoraVoiceError):
    def __init__(self, peak_vram_mib: int, limit_mib: int):
        self.peak_vram_mib = peak_vram_mib
        self.limit_mib = limit_mib
        super().__init__(
            f"RUNTIME_MEMORY_BLOCKED: process peak {peak_vram_mib} MiB; limit {limit_mib} MiB"
        )


class PandoraQueueFullError(PandoraVoiceError):
    def __init__(self, max_queued: int):
        self.max_queued = max_queued
        super().__init__(f"Pandora TTS queue is full ({max_queued} waiting requests)")


class PandoraModelNotLoadedError(PandoraVoiceError):
    pass


class PandoraReferenceNotFoundError(PandoraVoiceError):
    pass


class PandoraReferenceIntegrityError(PandoraVoiceError):
    pass


class PandoraSynthesisTimeoutError(PandoraVoiceError):
    pass
