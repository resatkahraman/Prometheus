from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import secrets
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

try:
    from aiohttp import web
except ModuleNotFoundError:  # Installed only in the isolated Pandora TTS environment.
    web = None

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.pandora_voice.chatterbox_v3_engine import ChatterboxV3Engine
from app.pandora_voice.config import PandoraVoiceConfig
from app.pandora_voice.errors import (
    PandoraGPUBusyError,
    PandoraMemoryError,
    PandoraQueueFullError,
    PandoraReferenceIntegrityError,
    PandoraReferenceNotFoundError,
    PandoraSynthesisTimeoutError,
    PandoraVoiceError,
)
from app.pandora_voice.models import PandoraAudioResult, PandoraVoiceMode
from app.pandora_voice.service import PandoraVoiceService


logging.basicConfig(level=logging.INFO, format="%(asctime)s [PandoraTTS] %(levelname)s %(message)s")
logger = logging.getLogger("pandora_tts_worker")

_CONFIG_PATH = _PROJECT_ROOT / "config" / "pandora_voice_models.json"
_CONFIG = PandoraVoiceConfig.from_models_json(_CONFIG_PATH)
_CONFIG = PandoraVoiceConfig(
    **{
        **_CONFIG.__dict__,
        "worker_port": int(os.environ.get("PANDORA_TTS_PORT", _CONFIG.worker_port)),
        "allow_model_download": os.environ.get("PANDORA_TTS_ALLOW_DOWNLOAD") == "1",
    }
)
_CONFIG.validate()

_TOKEN = secrets.token_urlsafe(32)
_ENGINE = ChatterboxV3Engine(_CONFIG)
_SERVICE = PandoraVoiceService(_CONFIG, _ENGINE)
_STARTED_AT = time.monotonic()
_TOTAL_REQUESTS = 0
_TOTAL_AUDIO_SECONDS = 0.0
_TOTAL_GENERATION_SECONDS = 0.0
_IDLE_WATCHDOG_KEY = (
    web.AppKey("pandora_idle_watchdog", asyncio.Task)
    if web is not None
    else "pandora_idle_watchdog"
)


def _secure_state_file() -> None:
    _CONFIG.runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "host": _CONFIG.worker_host,
        "port": _CONFIG.worker_port,
        "token": _TOKEN,
        "created_at_unix": time.time(),
    }
    temp = _CONFIG.worker_state_file.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, _CONFIG.worker_state_file)
    os.chmod(_CONFIG.worker_state_file, 0o600)
    if os.name == "nt":
        username = os.environ.get("USERNAME")
        if username:
            subprocess.run(
                [
                    "icacls",
                    str(_CONFIG.worker_state_file),
                    "/inheritance:r",
                    "/grant:r",
                    f"{username}:(R,W)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )


def _remove_state_file() -> None:
    try:
        data = json.loads(_CONFIG.worker_state_file.read_text(encoding="utf-8"))
        if int(data.get("pid", -1)) == os.getpid():
            _CONFIG.worker_state_file.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def _require_aiohttp():
    if web is None:
        raise RuntimeError(
            "aiohttp is required only in the isolated Pandora TTS environment. "
            "Run scripts/setup_pandora_tts.ps1 -Apply before starting the worker."
        )
    return web


def _has_valid_bearer(headers) -> bool:
    header = str(headers.get("Authorization", ""))
    supplied = header[7:] if header.startswith("Bearer ") else ""
    return bool(supplied) and secrets.compare_digest(supplied, _TOKEN)


def _require_auth(request: web.Request) -> None:
    if not _has_valid_bearer(request.headers):
        web_module = _require_aiohttp()
        raise web_module.HTTPUnauthorized(
            text=json.dumps({"error": "Unauthorized"}),
            content_type="application/json",
        )


def _combine_wav(results: list[PandoraAudioResult], pause_ms: int = 100) -> tuple[bytes, float]:
    if not results:
        raise ValueError("No audio results")
    sample_rate = results[0].sample_rate
    frames: list[bytes] = []
    total_frames = 0
    silence_frames = int(sample_rate * pause_ms / 1000)

    for index, result in enumerate(results):
        if result.sample_rate != sample_rate:
            raise ValueError("Chunk sample rates differ")
        with wave.open(io.BytesIO(result.audio_bytes), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                raise ValueError("Pandora chunks must be mono 16-bit PCM")
            payload = source.readframes(source.getnframes())
            total_frames += source.getnframes()
            frames.append(payload)
        if index + 1 < len(results):
            frames.append(b"\x00\x00" * silence_frames)
            total_frames += silence_frames

    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(b"".join(frames))
    return output.getvalue(), total_frames / sample_rate


def _error_response(exc: Exception) -> web.Response:
    if isinstance(exc, PandoraQueueFullError):
        status = 429
    elif isinstance(exc, PandoraGPUBusyError):
        status = 409
    elif isinstance(exc, (PandoraReferenceNotFoundError, PandoraReferenceIntegrityError)):
        status = 412
    elif isinstance(exc, PandoraSynthesisTimeoutError):
        status = 504
    elif isinstance(exc, PandoraMemoryError):
        status = 507
    elif isinstance(exc, (ValueError, TypeError)):
        status = 400
    else:
        status = 500
    if status >= 500:
        logger.exception("Pandora TTS request failed", exc_info=exc)
    return web.json_response({"error": type(exc).__name__, "detail": str(exc)}, status=status)


async def health(request: web.Request) -> web.Response:
    _require_auth(request)
    return web.json_response(
        {
            "status": "ok",
            "model_loaded": _ENGINE.is_loaded(),
            "voice_profile_hash": _ENGINE.voice_profile_hash,
            "poisoned": _SERVICE.poisoned_reason is not None,
            "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
        }
    )


async def metrics(request: web.Request) -> web.Response:
    _require_auth(request)
    response: dict[str, Any] = {
        "total_requests": _TOTAL_REQUESTS,
        "total_audio_seconds": round(_TOTAL_AUDIO_SECONDS, 3),
        "total_generation_seconds": round(_TOTAL_GENERATION_SECONDS, 3),
        "model_loaded": _ENGINE.is_loaded(),
    }
    try:
        import torch
        if torch.cuda.is_available():
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            response.update(
                {
                    "cuda_free_mib": int(free_bytes / 1024**2),
                    "cuda_total_mib": int(total_bytes / 1024**2),
                    "process_allocated_mib": int(torch.cuda.memory_allocated() / 1024**2),
                    "process_reserved_mib": int(torch.cuda.memory_reserved() / 1024**2),
                    "process_peak_reserved_mib": int(torch.cuda.max_memory_reserved() / 1024**2),
                }
            )
    except ImportError:
        pass
    return web.json_response(response)


async def voice_profile(request: web.Request) -> web.Response:
    _require_auth(request)
    if not _CONFIG.master_voice_profile.is_file():
        raise web.HTTPNotFound(
            text=json.dumps({"error": "No voice profile"}),
            content_type="application/json",
        )
    return web.json_response(json.loads(_CONFIG.master_voice_profile.read_text(encoding="utf-8")))


async def load_model(request: web.Request) -> web.Response:
    _require_auth(request)
    try:
        await _SERVICE.ensure_loaded()
        return web.json_response(
            {
                "status": "loaded",
                "sample_rate": _ENGINE.sample_rate,
                "voice_profile_hash": _ENGINE.voice_profile_hash,
            }
        )
    except Exception as exc:
        return _error_response(exc)


async def unload_model(request: web.Request) -> web.Response:
    _require_auth(request)
    try:
        unloaded = await _SERVICE.unload()
        return web.json_response({"status": "unloaded" if unloaded else "already_unloaded"})
    except Exception as exc:
        return _error_response(exc)


async def synthesize(request: web.Request) -> web.Response:
    global _TOTAL_REQUESTS, _TOTAL_AUDIO_SECONDS, _TOTAL_GENERATION_SECONDS
    _require_auth(request)
    try:
        body = await request.json()
        text = str(body.get("text", ""))
        mode = PandoraVoiceMode.parse(str(body.get("mode", "normal"))).value
        allow_cache = bool(body.get("allow_cache", True))
        if not text.strip():
            raise ValueError("text must not be empty")
        if len(text) > _CONFIG.max_input_chars:
            raise ValueError(f"text exceeds {_CONFIG.max_input_chars} characters")

        results = await _SERVICE.synthesize(text, mode=mode, allow_cache=allow_cache)
        wav_bytes, duration = _combine_wav(results)
        generation = sum(item.generation_time_seconds for item in results if not item.from_cache)
        _TOTAL_REQUESTS += 1
        _TOTAL_AUDIO_SECONDS += duration
        _TOTAL_GENERATION_SECONDS += generation
        rtf = generation / duration if duration else 0.0
        return web.Response(
            body=wav_bytes,
            content_type="audio/wav",
            headers={
                "X-Pandora-Voice-Profile": _ENGINE.voice_profile_hash,
                "X-Pandora-Sample-Rate": str(results[0].sample_rate),
                "X-Pandora-Duration-Seconds": f"{duration:.3f}",
                "X-Pandora-Generation-Seconds": f"{generation:.3f}",
                "X-Pandora-RTF": f"{rtf:.3f}",
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        return _error_response(exc)


async def idle_watchdog(app: web.Application) -> None:
    while True:
        await asyncio.sleep(30)
        try:
            await _SERVICE.unload_if_idle()
        except Exception:
            logger.exception("Pandora idle unload failed")


async def on_startup(app: web.Application) -> None:
    _secure_state_file()
    app[_IDLE_WATCHDOG_KEY] = asyncio.create_task(idle_watchdog(app))
    logger.info("Pandora TTS worker listening on loopback port %d.", _CONFIG.worker_port)
    if os.environ.get("PANDORA_TTS_PRELOAD") == "1":
        try:
            await _SERVICE.ensure_loaded()
        except Exception:
            logger.exception("Pandora preload failed")


async def on_cleanup(app: web.Application) -> None:
    task = app.get(_IDLE_WATCHDOG_KEY)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await _SERVICE.close()
    _remove_state_file()


def create_app() -> web.Application:
    web_module = _require_aiohttp()
    app = web_module.Application(client_max_size=32 * 1024)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics)
    app.router.add_get("/voice-profile", voice_profile)
    app.router.add_post("/load", load_model)
    app.router.add_post("/synthesize", synthesize)
    app.router.add_post("/unload", unload_model)
    return app


def main() -> None:
    web_module = _require_aiohttp()
    web_module.run_app(
        create_app(),
        host=_CONFIG.worker_host,
        port=_CONFIG.worker_port,
        print=None,
        access_log=None,
    )


if __name__ == "__main__":
    main()
