from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from threading import RLock
from typing import Callable

from fastapi import Request
from pydantic import BaseModel, Field, field_validator


PANDORA_SESSION_COOKIE_NAME = "prometheus_pandora_session"
PANDORA_SESSION_COOKIE_PATH = "/v1/pandora"
PANDORA_PAIRING_TTL_SECONDS = 300
PANDORA_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
PANDORA_MAX_DEVICES = 5
PANDORA_MAX_PAIRING_ATTEMPTS = 5

PANDORA_PAIRING_REQUIRED_DETAIL = "Pandora eşleştirmesi gerekli."
PANDORA_PAIRING_INVALID_DETAIL = (
    "Eşleştirme kodu geçersiz, kullanılmış veya süresi dolmuş."
)
PANDORA_PAIRING_LOCAL_ONLY_DETAIL = (
    "Eşleştirme kodu yalnızca Prometheus'un çalıştığı bilgisayardan oluşturulabilir."
)
PANDORA_REMOTE_ACCESS_REQUIRED_DETAIL = (
    "Pandora eşleştirmesi için uzak HTTP erişimi etkin olmalı."
)
PANDORA_DEVICE_LIMIT_DETAIL = (
    "Pandora cihaz sınırına ulaşıldı. Yeni cihaz eşleştirmeden önce mevcut "
    "bir oturum kapatılmalı."
)


class PandoraPairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    device_name: str = Field(default="Pandora cihazı", min_length=1, max_length=64)

    @field_validator("device_name")
    @classmethod
    def normalize_device_name(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        return normalized or "Pandora cihazı"


class PandoraPairingRejectedError(RuntimeError):
    pass


class PandoraDeviceLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class PandoraSessionInfo:
    device_name: str
    created_at: float
    expires_at: float


@dataclass
class _PairingCode:
    digest: bytes
    expires_at: float
    remaining_attempts: int


class PandoraSessionManager:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        pairing_ttl_seconds: int = PANDORA_PAIRING_TTL_SECONDS,
        session_ttl_seconds: int = PANDORA_SESSION_TTL_SECONDS,
        max_devices: int = PANDORA_MAX_DEVICES,
        max_pairing_attempts: int = PANDORA_MAX_PAIRING_ATTEMPTS,
    ) -> None:
        self._clock = clock
        self._pairing_ttl_seconds = pairing_ttl_seconds
        self._session_ttl_seconds = session_ttl_seconds
        self._max_devices = max_devices
        self._max_pairing_attempts = max_pairing_attempts
        self._pairing_code: _PairingCode | None = None
        self._sessions: dict[bytes, PandoraSessionInfo] = {}
        self._lock = RLock()

    @property
    def pairing_ttl_seconds(self) -> int:
        return self._pairing_ttl_seconds

    @property
    def session_ttl_seconds(self) -> int:
        return self._session_ttl_seconds

    @staticmethod
    def _digest(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    def _cleanup_locked(self, now: float) -> None:
        if self._pairing_code and self._pairing_code.expires_at <= now:
            self._pairing_code = None
        expired = [
            digest
            for digest, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for digest in expired:
            self._sessions.pop(digest, None)

    def issue_pairing_code(self) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._clock()
        with self._lock:
            self._cleanup_locked(now)
            self._pairing_code = _PairingCode(
                digest=self._digest(code),
                expires_at=now + self._pairing_ttl_seconds,
                remaining_attempts=self._max_pairing_attempts,
            )
        return code

    def create_session(self, *, code: str, device_name: str) -> str:
        now = self._clock()
        normalized_code = code.strip()
        with self._lock:
            self._cleanup_locked(now)
            pairing = self._pairing_code
            if pairing is None:
                raise PandoraPairingRejectedError(
                    PANDORA_PAIRING_INVALID_DETAIL
                )

            pairing.remaining_attempts -= 1
            candidate_digest = self._digest(normalized_code)
            valid = secrets.compare_digest(
                candidate_digest,
                pairing.digest,
            )
            if not valid:
                if pairing.remaining_attempts <= 0:
                    self._pairing_code = None
                raise PandoraPairingRejectedError(
                    PANDORA_PAIRING_INVALID_DETAIL
                )

            self._pairing_code = None
            if len(self._sessions) >= self._max_devices:
                raise PandoraDeviceLimitError(PANDORA_DEVICE_LIMIT_DETAIL)

            token = secrets.token_urlsafe(32)
            self._sessions[self._digest(token)] = PandoraSessionInfo(
                device_name=device_name,
                created_at=now,
                expires_at=now + self._session_ttl_seconds,
            )
            return token

    def session_for_token(self, token: str | None) -> PandoraSessionInfo | None:
        if not token:
            return None
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            return self._sessions.get(digest)

    def revoke(self, token: str | None) -> bool:
        if not token:
            return False
        digest = self._digest(token)
        with self._lock:
            return self._sessions.pop(digest, None) is not None

    def active_session_count(self) -> int:
        now = self._clock()
        with self._lock:
            self._cleanup_locked(now)
            return len(self._sessions)


def request_pandora_session_token(request: Request) -> str | None:
    token = request.cookies.get(PANDORA_SESSION_COOKIE_NAME)
    return token.strip() if token else None
