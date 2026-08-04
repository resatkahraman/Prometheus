from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable

from app.pandora_voice.cache import PandoraAudioCache
from app.pandora_voice.config import PandoraVoiceConfig
from app.pandora_voice.engine import PandoraVoiceEngine
from app.pandora_voice.errors import PandoraQueueFullError, PandoraSynthesisTimeoutError
from app.pandora_voice.models import PandoraAudioResult, PandoraVoiceMode
from app.pandora_voice.normalization import chunk_text, make_speak_text, normalize_for_tts

logger = logging.getLogger(__name__)


class PandoraVoiceService:
    def __init__(self, config: PandoraVoiceConfig, engine: PandoraVoiceEngine) -> None:
        config.validate()
        self.config = config
        self.engine = engine
        self.cache = PandoraAudioCache(config)
        self._active_lock = asyncio.Lock()
        self._queue_guard = asyncio.Lock()
        self._in_system = 0
        self._last_activity = time.monotonic()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pandora-tts")
        self._poisoned_reason: str | None = None

    async def _reserve_queue_slot(self) -> None:
        async with self._queue_guard:
            capacity = 1 + self.config.max_queued_requests
            if self._in_system >= capacity:
                raise PandoraQueueFullError(self.config.max_queued_requests)
            self._in_system += 1

    async def _release_queue_slot(self) -> None:
        async with self._queue_guard:
            self._in_system = max(0, self._in_system - 1)

    async def _blocking(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._executor, partial(function, *args, **kwargs))
        try:
            return await asyncio.wait_for(
                asyncio.shield(future),
                timeout=self.config.request_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            # Python cannot safely kill a running inference thread. Poison this
            # worker so no second CUDA inference can overlap it. Restarting the
            # dedicated worker process is the only supported recovery.
            self._poisoned_reason = (
                f"Previous Pandora inference exceeded {self.config.request_timeout_seconds:.0f}s; "
                "restart the local TTS worker"
            )
            raise PandoraSynthesisTimeoutError(self._poisoned_reason) from exc

    def _ensure_healthy(self) -> None:
        if self._poisoned_reason:
            raise PandoraSynthesisTimeoutError(self._poisoned_reason)

    @property
    def poisoned_reason(self) -> str | None:
        return self._poisoned_reason

    async def ensure_loaded(self) -> None:
        self._ensure_healthy()
        if self.engine.is_loaded():
            return
        async with self._active_lock:
            self._ensure_healthy()
            if not self.engine.is_loaded():
                await self._blocking(self.engine.load)

    async def synthesize(
        self,
        text: str,
        *,
        mode: str = "normal",
        allow_cache: bool = True,
    ) -> list[PandoraAudioResult]:
        self._ensure_healthy()
        voice_mode = PandoraVoiceMode.parse(mode)
        normalized = normalize_for_tts(text, max_chars=self.config.max_input_chars)
        chunks = chunk_text(
            normalized,
            target_chars=self.config.chunk_target_chars,
            hard_max_chars=self.config.chunk_hard_max_chars,
        )
        if not chunks:
            return []

        await self._reserve_queue_slot()
        try:
            async with self._active_lock:
                self._ensure_healthy()
                if not self.engine.is_loaded():
                    await self._blocking(self.engine.load)
                results: list[PandoraAudioResult] = []
                for index, chunk in enumerate(chunks):
                    cached = (
                        self.cache.get(chunk, voice_mode.value, self.engine.voice_profile_hash)
                        if allow_cache
                        else None
                    )
                    if cached is None:
                        generated = await self._blocking(
                            self.engine.synthesize,
                            chunk,
                            mode=voice_mode.value,
                        )
                        if allow_cache:
                            self.cache.put(chunk, generated)
                    else:
                        generated = cached

                    results.append(
                        PandoraAudioResult(
                            audio_bytes=generated.audio_bytes,
                            sample_rate=generated.sample_rate,
                            duration_seconds=generated.duration_seconds,
                            mode=generated.mode,
                            voice_profile_hash=generated.voice_profile_hash,
                            generation_time_seconds=generated.generation_time_seconds,
                            from_cache=generated.from_cache,
                            chunk_index=index,
                            total_chunks=len(chunks),
                        )
                    )
                return results
        finally:
            await self._release_queue_slot()
            self._last_activity = time.monotonic()

    async def get_speak_text(self, full_text: str) -> str:
        return make_speak_text(full_text)

    async def unload(self) -> bool:
        self._ensure_healthy()
        async with self._active_lock:
            if not self.engine.is_loaded():
                return False
            await self._blocking(self.engine.unload)
            self._last_activity = time.monotonic()
            return True

    async def unload_if_idle(self) -> bool:
        if self._poisoned_reason:
            return False
        elapsed = time.monotonic() - self._last_activity
        if elapsed < self.config.idle_unload_seconds or not self.engine.is_loaded():
            return False
        if self._active_lock.locked():
            return False
        async with self._active_lock:
            if self.engine.is_loaded():
                await self._blocking(self.engine.unload)
                logger.info("Pandora voice engine unloaded after %.0f seconds idle.", elapsed)
                return True
        return False

    async def close(self) -> None:
        if not self._poisoned_reason and self.engine.is_loaded():
            async with self._active_lock:
                await self._blocking(self.engine.unload)
        self._executor.shutdown(wait=False, cancel_futures=True)
